import { HttpError } from "../../middleware/errorHandler.js";
import { Session, type SessionStatus } from "./session.model.js";

export async function startSession(userId: string, subject: string, plannedDurationMinutes: number) {
  const activeExisting = await Session.findOne({ userId, status: "active" });
  if (activeExisting) {
    throw new HttpError(409, "You already have an active session - end or abandon it first");
  }

  return Session.create({ userId, subject, plannedDurationMinutes, startedAt: new Date() });
}

export async function getSession(userId: string, sessionId: string) {
  const session = await Session.findOne({ _id: sessionId, userId });
  if (!session) throw new HttpError(404, "Session not found");
  return session;
}

export async function listSessions(userId: string, limit = 20) {
  return Session.find({ userId }).sort({ createdAt: -1 }).limit(limit);
}

export async function setSessionStatus(sessionId: string, status: SessionStatus, extra: Record<string, unknown> = {}) {
  const session = await Session.findByIdAndUpdate(sessionId, { status, ...extra }, { new: true });
  if (!session) throw new HttpError(404, "Session not found");
  return session;
}

export async function abandonSession(userId: string, sessionId: string) {
  const session = await getSession(userId, sessionId);
  if (session.status !== "active") {
    throw new HttpError(400, "Only active sessions can be abandoned");
  }
  return setSessionStatus(sessionId, "abandoned", { endedAt: new Date() });
}

/** Most recent completed session for a subject, used to diff note snapshots against. */
export async function getPreviousCompletedSession(userId: string, subject: string, beforeSessionId: string) {
  return Session.findOne({
    userId,
    subject,
    status: "completed",
    _id: { $ne: beforeSessionId },
  }).sort({ createdAt: -1 });
}
