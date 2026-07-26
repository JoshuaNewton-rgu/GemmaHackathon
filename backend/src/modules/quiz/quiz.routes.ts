import { Router } from "express";
import { requireAuth } from "../../middleware/authMiddleware.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { generateBreakQuiz, listQuizzes, submitAnswers } from "./quiz.controller.js";

export const quizRouter = Router();

quizRouter.use(requireAuth);
quizRouter.get("/", asyncHandler(listQuizzes));
// Session-recall quizzes are created server-side right after notes upload (see notes.routes.ts);
// this route only covers break-gate quizzes, which a student can request any time.
quizRouter.post("/break", asyncHandler(generateBreakQuiz));
quizRouter.post("/:quizId/answers", asyncHandler(submitAnswers));
