import type { Response } from "express";
import { z } from "zod";
import type { AuthedRequest } from "../../middleware/authMiddleware.js";
import { abandonSession, getSession, listSessions, startSession } from "./session.service.js";

const startSchema = z.object({
  subject: z.string().min(1),
  plannedDurationMinutes: z.number().int().min(5).max(180).default(30),
});

export async function start(req: AuthedRequest, res: Response) {
  const body = startSchema.parse(req.body);
  const session = await startSession(req.userId!, body.subject, body.plannedDurationMinutes);
  res.status(201).json({ session });
}

export async function list(req: AuthedRequest, res: Response) {
  const sessions = await listSessions(req.userId!);
  res.json({ sessions });
}

export async function getOne(req: AuthedRequest, res: Response) {
  const session = await getSession(req.userId!, req.params.id);
  res.json({ session });
}

export async function abandon(req: AuthedRequest, res: Response) {
  const session = await abandonSession(req.userId!, req.params.id);
  res.json({ session });
}
