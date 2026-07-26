import cors from "cors";
import express from "express";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { env } from "./config/env.js";
import { errorHandler, notFoundHandler } from "./middleware/errorHandler.js";
import { authRouter } from "./modules/auth/auth.routes.js";
import { coachRouter } from "./modules/coach/coach.routes.js";
import { notesRouter } from "./modules/notes/notes.routes.js";
import { quizRouter } from "./modules/quiz/quiz.routes.js";
import { sessionRouter } from "./modules/session/session.routes.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export function createApp() {
  const app = express();

  app.use(cors({ origin: env.corsOrigin }));
  app.use(express.json());
  app.use("/uploads", express.static(path.resolve(__dirname, "../uploads")));

  app.get("/health", (_req, res) => res.json({ ok: true, gemmaProvider: env.gemma.provider, gemmaModel: env.gemma.model }));

  app.use("/auth", authRouter);
  app.use("/sessions", sessionRouter);
  // notesRouter defines its own "/sessions/:sessionId/notes" path, so it's mounted at root.
  app.use(notesRouter);
  app.use("/quiz", quizRouter);
  app.use("/coach", coachRouter);

  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
}
