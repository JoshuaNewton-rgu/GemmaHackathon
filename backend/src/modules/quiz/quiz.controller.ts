import type { Response } from "express";
import { z } from "zod";
import type { AuthedRequest } from "../../middleware/authMiddleware.js";
import { HttpError } from "../../middleware/errorHandler.js";
import { User } from "../auth/auth.model.js";
import { createCoachMessage, summarizeBreakOutcome } from "../coach/coach.service.js";
import { applyBreakOutcome, applyQuizRewards, saveUserRewards } from "../gamification/gamification.service.js";
import { getLatestSnapshotsForSubject } from "../notes/notes.service.js";
import { Session } from "../session/session.model.js";
import { Quiz } from "./quiz.model.js";
import { createQuiz, gradeQuiz, toPublicQuiz } from "./quiz.service.js";

const BREAK_QUIZ_QUESTION_COUNT = 5;
// Pass threshold (3/5) is enforced in quiz.service.gradeQuiz via `passed`.
const FULL_BREAK_MINUTES = 15;
const REVIEW_BREAK_MINUTES = 5;

const generateBreakQuizSchema = z.object({ subject: z.string().min(1) });
const submitAnswersSchema = z.object({
  answers: z.array(z.object({ questionId: z.string(), selectedIndex: z.number().int().min(0).max(3) })),
});

export async function listQuizzes(req: AuthedRequest, res: Response) {
  const quizzes = await Quiz.find({ userId: req.userId, submittedAt: { $ne: null } })
    .sort({ createdAt: -1 })
    .limit(30);
  res.json({ quizzes });
}

export async function generateBreakQuiz(req: AuthedRequest, res: Response) {
  const { subject } = generateBreakQuizSchema.parse(req.body);
  const userId = req.userId!;

  const snapshots = await getLatestSnapshotsForSubject(userId, subject, 3);
  if (snapshots.length === 0) {
    throw new HttpError(400, "No notes found for this subject yet - complete a study session first");
  }

  const combinedText = snapshots
    .map((s) => s.ocrText)
    .reverse()
    .join("\n\n---\n\n");

  const user = await User.findById(userId);
  if (!user) throw new HttpError(404, "User not found");

  const mostRecentSession = await Session.findOne({ userId, subject, status: "completed" }).sort({ createdAt: -1 });

  const quiz = await createQuiz({
    userId,
    sessionId: mostRecentSession ? String(mostRecentSession._id) : null,
    subject,
    kind: "break",
    noteText: combinedText,
    userLevel: user.level,
    questionCount: BREAK_QUIZ_QUESTION_COUNT,
  });

  res.status(201).json({ quiz: toPublicQuiz(quiz) });
}

export async function submitAnswers(req: AuthedRequest, res: Response) {
  const { answers } = submitAnswersSchema.parse(req.body);
  const userId = req.userId!;

  const quiz = await gradeQuiz(userId, req.params.quizId, answers);
  const total = quiz.questions.length;
  const correctCount = quiz.correctCount ?? 0;

  const user = await User.findById(userId);
  if (!user) throw new HttpError(404, "User not found");

  const xpAwarded = applyQuizRewards(user, correctCount, total);

  if (quiz.kind === "break") {
    const passed = applyBreakOutcome(user, { correctCount, total });
    await saveUserRewards(user);

    const { type, summary } = summarizeBreakOutcome(passed, correctCount, total);
    const coachMessage = await createCoachMessage({
      userId,
      sessionId: quiz.sessionId ? String(quiz.sessionId) : undefined,
      persona: user.persona,
      type,
      contextSummary: summary,
    });

    res.json({
      quiz,
      passed,
      breakMinutes: passed ? FULL_BREAK_MINUTES : REVIEW_BREAK_MINUTES,
      coachMessage,
      xpAwarded,
    });
    return;
  }

  await saveUserRewards(user);
  res.json({ quiz, xpAwarded });
}
