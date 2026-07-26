import type { NextFunction, Request, Response } from "express";
import { logger } from "../utils/logger.js";

export class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function notFoundHandler(req: Request, res: Response): void {
  res.status(404).json({ error: `Not found: ${req.method} ${req.path}` });
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function errorHandler(err: unknown, req: Request, res: Response, next: NextFunction): void {
  const status = err instanceof HttpError ? err.status : 500;
  const message = err instanceof Error ? err.message : "Unknown error";

  if (status >= 500) {
    logger.error("Unhandled error", { message, path: req.path });
  }

  res.status(status).json({ error: message });
}
