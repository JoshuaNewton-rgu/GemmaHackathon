import { Router } from "express";
import { requireAuth } from "../../middleware/authMiddleware.js";
import { uploadNoteImage } from "../../middleware/upload.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { uploadNotes } from "./notes.controller.js";

export const notesRouter = Router();

notesRouter.use(requireAuth);
notesRouter.post("/sessions/:sessionId/notes", uploadNoteImage.single("image"), asyncHandler(uploadNotes));
