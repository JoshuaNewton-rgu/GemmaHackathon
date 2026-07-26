import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { env } from "../../config/env.js";
import { HttpError } from "../../middleware/errorHandler.js";
import { PERSONAS, User, type Persona } from "./auth.model.js";

const SALT_ROUNDS = 10;

function signToken(userId: string): string {
  return jwt.sign({ sub: userId }, env.jwtSecret, { expiresIn: "30d" });
}

export async function registerUser(email: string, password: string, name: string) {
  const existing = await User.findOne({ email: email.toLowerCase() });
  if (existing) {
    throw new HttpError(409, "An account with that email already exists");
  }

  const passwordHash = await bcrypt.hash(password, SALT_ROUNDS);
  const user = await User.create({ email, passwordHash, name });

  return { user, token: signToken(user.id) };
}

export async function loginUser(email: string, password: string) {
  const user = await User.findOne({ email: email.toLowerCase() });
  if (!user) {
    throw new HttpError(401, "Invalid email or password");
  }

  const valid = await bcrypt.compare(password, user.passwordHash);
  if (!valid) {
    throw new HttpError(401, "Invalid email or password");
  }

  return { user, token: signToken(user.id) };
}

export async function setPersona(userId: string, persona: Persona) {
  if (!PERSONAS.includes(persona)) {
    throw new HttpError(400, `persona must be one of: ${PERSONAS.join(", ")}`);
  }
  const user = await User.findByIdAndUpdate(userId, { persona }, { new: true });
  if (!user) throw new HttpError(404, "User not found");
  return user;
}

export function toPublicUser(user: {
  id: string;
  email: string;
  name: string;
  persona: string;
  level: number;
  xp: number;
  stats: unknown;
  streak: unknown;
  achievements: string[];
}) {
  const { id, email, name, persona, level, xp, stats, streak, achievements } = user;
  return { id, email, name, persona, level, xp, stats, streak, achievements };
}
