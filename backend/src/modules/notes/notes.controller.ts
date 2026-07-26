import type { Response } from "express";
import type { AuthedRequest } from "../../middleware/authMiddleware.js";
import { HttpError } from "../../middleware/errorHandler.js";
import { submitSessionNotes } from "./notes.service.js";

export async function uploadNotes(req: AuthedRequest, res: Response) {
  const file = req.file;
  if (!file) {
    throw new HttpError(400, "No image uploaded (field name must be 'image')");
  }

  const result = await submitSessionNotes({
    userId: req.userId!,
    sessionId: req.params.sessionId,
    imagePath: file.path,
    imageUrl: `/uploads/${file.filename}`,
    mimeType: file.mimetype,
  });

  res.status(201).json(result);
}
