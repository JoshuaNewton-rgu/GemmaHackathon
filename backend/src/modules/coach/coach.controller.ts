import type { Response } from "express";
import type { AuthedRequest } from "../../middleware/authMiddleware.js";
import { CoachMessage } from "./coach.model.js";

export async function listMessages(req: AuthedRequest, res: Response) {
  const messages = await CoachMessage.find({ userId: req.userId }).sort({ createdAt: -1 }).limit(20);
  res.json({ messages });
}
