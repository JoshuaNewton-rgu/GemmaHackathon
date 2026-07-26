import type { Response } from "express";
import { z } from "zod";
import type { AuthedRequest } from "../../middleware/authMiddleware.js";
import { HttpError } from "../../middleware/errorHandler.js";
import { loginUser, registerUser, setPersona, toPublicUser } from "./auth.service.js";
import { User } from "./auth.model.js";

const registerSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  name: z.string().min(1),
});

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

const personaSchema = z.object({
  persona: z.enum(["scottish_granny", "disappointed_mother", "angry_father"]),
});

export async function register(req: AuthedRequest, res: Response) {
  const body = registerSchema.parse(req.body);
  const { user, token } = await registerUser(body.email, body.password, body.name);
  res.status(201).json({ user: toPublicUser(user), token });
}

export async function login(req: AuthedRequest, res: Response) {
  const body = loginSchema.parse(req.body);
  const { user, token } = await loginUser(body.email, body.password);
  res.json({ user: toPublicUser(user), token });
}

export async function me(req: AuthedRequest, res: Response) {
  const user = await User.findById(req.userId);
  if (!user) throw new HttpError(404, "User not found");
  res.json({ user: toPublicUser(user) });
}

export async function updatePersona(req: AuthedRequest, res: Response) {
  const body = personaSchema.parse(req.body);
  const user = await setPersona(req.userId!, body.persona);
  res.json({ user: toPublicUser(user) });
}
