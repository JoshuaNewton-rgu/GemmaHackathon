import { Router } from "express";
import { requireAuth } from "../../middleware/authMiddleware.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { abandon, getOne, list, start } from "./session.controller.js";

export const sessionRouter = Router();

sessionRouter.use(requireAuth);
sessionRouter.post("/", asyncHandler(start));
sessionRouter.get("/", asyncHandler(list));
sessionRouter.get("/:id", asyncHandler(getOne));
sessionRouter.post("/:id/abandon", asyncHandler(abandon));
