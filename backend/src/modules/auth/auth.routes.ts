import { Router } from "express";
import { requireAuth } from "../../middleware/authMiddleware.js";
import { asyncHandler } from "../../utils/asyncHandler.js";
import { login, me, register, updatePersona } from "./auth.controller.js";

export const authRouter = Router();

authRouter.post("/register", asyncHandler(register));
authRouter.post("/login", asyncHandler(login));
authRouter.get("/me", requireAuth, asyncHandler(me));
authRouter.patch("/persona", requireAuth, asyncHandler(updatePersona));
