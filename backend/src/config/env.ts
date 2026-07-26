import dotenv from "dotenv";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load backend/.env first, then fall back to the repo-root .env so an
// existing root-level GEMINI_API_KEY (e.g. from early hackathon testing)
// keeps working without duplicating secrets.
dotenv.config({ path: path.resolve(__dirname, "../../.env") });
dotenv.config({ path: path.resolve(__dirname, "../../../.env") });

function required(name: string, fallback?: string): string {
  const value = process.env[name] ?? fallback;
  if (value === undefined) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export const env = {
  port: Number(process.env.PORT ?? 4000),
  nodeEnv: process.env.NODE_ENV ?? "development",
  jwtSecret: process.env.JWT_SECRET ?? "dev-secret-change-me",
  corsOrigin: process.env.CORS_ORIGIN ?? "*",

  mongodbUri: process.env.MONGODB_URI ?? "mongodb://localhost:27017/proofstudy",

  gemma: {
    provider: (process.env.GEMMA_PROVIDER ?? "gemini_api") as "gemini_api" | "self_hosted",
    model: process.env.GEMMA_MODEL ?? "gemma-4-31b-it",
    geminiApiKey: process.env.GEMINI_API_KEY,
    selfHostedUrl: process.env.SELF_HOSTED_GEMMA_URL ?? "http://localhost:11434",
  },

  tts: {
    provider: (process.env.TTS_PROVIDER ?? "device") as "device" | "elevenlabs",
    elevenLabsApiKey: process.env.ELEVENLABS_API_KEY,
  },
};

export { required };
