import type { HydratedDocument } from "mongoose";
import { User, type UserDoc } from "../auth/auth.model.js";
import { computeQuizXp, computeSessionXp } from "../../utils/scoring.js";

type UserHydrated = HydratedDocument<UserDoc>;

const XP_PER_LEVEL = 100;

function todayKey(): string {
  return new Date().toISOString().slice(0, 10); // YYYY-MM-DD
}

function yesterdayKey(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

function addXp(user: UserHydrated, xp: number) {
  user.xp += xp;
  user.level = Math.floor(user.xp / XP_PER_LEVEL) + 1;
}

/** Applies XP, recomputes level, bumps discipline/knowledge stats for a completed study session (notes uploaded). */
export function applySessionRewards(
  user: UserHydrated,
  params: { progressScore: number; newKeywordCount: number },
) {
  const xp = computeSessionXp(params.progressScore);
  addXp(user, xp);
  user.stats.discipline += 1;
  user.stats.focus += params.progressScore >= 60 ? 1 : 0;
  user.stats.knowledge += params.newKeywordCount;

  if (params.progressScore >= 80) {
    user.achievementProgress.highProgressSessions += 1;
  }

  updateStreak(user);
  checkAchievements(user);

  return xp;
}

/** Extra XP once a quiz (session recall or break-gate) is graded. */
export function applyQuizRewards(user: UserHydrated, correctCount: number, total: number) {
  const xp = computeQuizXp(correctCount, total);
  addXp(user, xp);
  user.stats.knowledge += Math.round((correctCount / total) * 2);
  return xp;
}

export function updateStreak(user: UserHydrated) {
  const today = todayKey();
  const yesterday = yesterdayKey();

  if (user.streak.lastCompletedDate === today) {
    return; // already counted today
  }
  if (user.streak.lastCompletedDate === yesterday) {
    user.streak.current += 1;
  } else {
    user.streak.current = 1;
  }
  user.streak.lastCompletedDate = today;
  user.streak.longest = Math.max(user.streak.longest, user.streak.current);
  user.stats.consistency = user.streak.current;
}

/** Called after a break quiz is graded, to award XP/streak credit and track break-related achievements. */
export function applyBreakOutcome(user: UserHydrated, params: { correctCount: number; total: number }) {
  const passed = params.correctCount / params.total >= 0.6;
  if (passed && params.correctCount >= 4) {
    user.achievementProgress.highScoreBreaksEarned += 1;
  }
  checkAchievements(user);
  return passed;
}

function grant(user: UserHydrated, achievement: string) {
  if (!user.achievements.includes(achievement)) {
    user.achievements.push(achievement);
  }
}

function checkAchievements(user: UserHydrated) {
  if (user.achievementProgress.highProgressSessions >= 10) {
    grant(user, "Proof machine");
  }
  if (user.achievementProgress.highScoreBreaksEarned >= 20) {
    grant(user, "Boss crusher");
  }
  if (user.streak.current >= 1) {
    // "Honest notes" is awarded per-day elsewhere (notes.service tracks same-day uploads);
    // streak >= 1 is the minimum precondition checked here for cheap re-evaluation.
  }
}

export async function saveUserRewards(user: UserHydrated) {
  await User.updateOne(
    { _id: user._id },
    {
      xp: user.xp,
      level: user.level,
      stats: user.stats,
      streak: user.streak,
      achievements: user.achievements,
      achievementProgress: user.achievementProgress,
    },
  );
}
