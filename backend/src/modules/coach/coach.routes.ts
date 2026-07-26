import { Router } from "express";
import { requireAuth } from "../../middleware/authMiddleware.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { listMessages } from "./coach.controller.js";

export const coachRouter = Router();

coachRouter.use(requireAuth);
coachRouter.get("/messages", asyncHandler(listMessages));
