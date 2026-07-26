import fs from "node:fs/promises";
import { getOcrProvider } from "../../config/ocr.js";
import { HttpError } from "../../middleware/errorHandler.js";
import { computeProgressScore } from "../../utils/scoring.js";
import { User } from "../auth/auth.model.js";
import { createCoachMessage, summarizeSessionOutcome } from "../coach/coach.service.js";
import { applySessionRewards, saveUserRewards } from "../gamification/gamification.service.js";
import { createQuiz, toPublicQuiz } from "../quiz/quiz.service.js";
import { getPreviousCompletedSession, getSession, setSessionStatus } from "../session/session.service.js";
import { NoteSnapshot } from "./notes.model.js";

const SESSION_QUIZ_QUESTION_COUNT = 5;

export async function getLatestSnapshotsForSubject(userId: string, subject: string, limit = 3) {
  return NoteSnapshot.find({ userId, subject }).sort({ createdAt: -1 }).limit(limit);
}

export async function submitSessionNotes(params: {
  userId: string;
  sessionId: string;
  imagePath: string;
  imageUrl: string;
  mimeType: string;
}) {
  const session = await getSession(params.userId, params.sessionId);
  if (session.status !== "active") {
    throw new HttpError(400, "Session is not active - start a new session before uploading notes");
  }

  const imageBuffer = await fs.readFile(params.imagePath);
  const imageBase64 = imageBuffer.toString("base64");

  const ocr = await getOcrProvider().extractText(imageBase64, params.mimeType);
  const wordCount = ocr.text.trim().split(/\s+/).filter(Boolean).length;

  const noteSnapshot = await NoteSnapshot.create({
    sessionId: session._id,
    userId: params.userId,
    subject: session.subject,
    imageUrl: params.imageUrl,
    ocrText: ocr.text,
    headings: ocr.headings,
    keywords: ocr.keywords,
    wordCount,
  });

  const previousSession = await getPreviousCompletedSession(params.userId, session.subject, String(session._id));
  const previousSnapshot = previousSession
    ? await NoteSnapshot.findOne({ sessionId: previousSession._id }).sort({ createdAt: -1 })
    : null;

  const actualDurationMinutes = (Date.now() - session.startedAt.getTime()) / 60000;
  const breakdown = computeProgressScore({
    previousWordCount: previousSnapshot?.wordCount ?? 0,
    currentWordCount: wordCount,
    previousKeywords: previousSnapshot?.keywords ?? [],
    currentKeywords: ocr.keywords,
    plannedDurationMinutes: session.plannedDurationMinutes,
    actualDurationMinutes,
  });

  const user = await User.findById(params.userId);
  if (!user) throw new HttpError(404, "User not found");

  const [quiz, coachMessage] = await Promise.all([
    createQuiz({
      userId: params.userId,
      sessionId: String(session._id),
      subject: session.subject,
      kind: "session",
      noteText: ocr.text,
      userLevel: user.level,
      questionCount: SESSION_QUIZ_QUESTION_COUNT,
    }),
    (async () => {
      const { type, summary } = summarizeSessionOutcome(breakdown.score);
      return createCoachMessage({
        userId: params.userId,
        sessionId: String(session._id),
        persona: user.persona,
        type,
        contextSummary: summary,
      });
    })(),
  ]);

  const xpAwarded = applySessionRewards(user, {
    progressScore: breakdown.score,
    newKeywordCount: breakdown.newKeywordCount,
  });
  await saveUserRewards(user);

  const updatedSession = await setSessionStatus(String(session._id), "completed", {
    endedAt: new Date(),
    progressScore: breakdown.score,
    xpAwarded,
  });

  return {
    session: updatedSession,
    noteSnapshot,
    progressBreakdown: breakdown,
    quiz: toPublicQuiz(quiz),
    coachMessage,
    xpAwarded,
  };
}
