import { GoogleGenAI } from "@google/genai";
import { env } from "./env.js";
import { logger } from "../utils/logger.js";

export interface GemmaTextParams {
  prompt: string;
  systemInstruction?: string;
}

export interface GemmaJsonParams extends GemmaTextParams {
  /** Plain-English description of the JSON shape expected back, injected into the prompt. */
  schemaDescription?: string;
}

export interface GemmaImageParams extends GemmaTextParams {
  imageBase64: string;
  mimeType: string;
}

export interface GemmaClient {
  generateText(params: GemmaTextParams): Promise<string>;
  generateJson<T>(params: GemmaJsonParams): Promise<T>;
  generateFromImage(params: GemmaImageParams): Promise<string>;
}

/**
 * Strips ```json fences (models love to add them even when told not to) and
 * parses the remaining text as JSON.
 */
function parseJsonResponse<T>(raw: string): T {
  const cleaned = raw
    .trim()
    .replace(/^```(?:json)?/i, "")
    .replace(/```$/, "")
    .trim();
  try {
    return JSON.parse(cleaned) as T;
  } catch (err) {
    throw new Error(`Gemma 4 did not return valid JSON: ${cleaned.slice(0, 300)}`);
  }
}

function jsonInstruction(schemaDescription?: string): string {
  return [
    "Respond with ONLY valid JSON matching this shape, no prose, no markdown code fences.",
    schemaDescription ? `Shape: ${schemaDescription}` : "",
  ]
    .filter(Boolean)
    .join(" ");
}

/**
 * Gemini API-hosted Gemma 4 (aistudio.google.com). This is the fastest path
 * to a working demo: no GPU, no local weights, pay-per-use.
 *
 * Note: some environments issue Gemini API keys that the SDK's client-side
 * validation rejects as "not a valid API key" even though the backend
 * accepts them fine over the wire. Passing a well-formed dummy key and
 * forcing the real key via the `x-goog-api-key` header (as proven out in
 * the original hackathon smoke test) sidesteps that without any behaviour
 * change for normal keys.
 */
class GeminiApiGemmaClient implements GemmaClient {
  private readonly ai: GoogleGenAI;

  constructor(apiKey: string, private readonly model: string) {
    this.ai = new GoogleGenAI({
      apiKey: "AIza_dummy_key",
      httpOptions: { headers: { "x-goog-api-key": apiKey } },
    });
  }

  async generateText({ prompt, systemInstruction }: GemmaTextParams): Promise<string> {
    const response = await this.ai.models.generateContent({
      model: this.model,
      contents: prompt,
      config: systemInstruction ? { systemInstruction } : undefined,
    });
    return response.text ?? "";
  }

  async generateJson<T>({ prompt, systemInstruction, schemaDescription }: GemmaJsonParams): Promise<T> {
    const response = await this.ai.models.generateContent({
      model: this.model,
      contents: `${prompt}\n\n${jsonInstruction(schemaDescription)}`,
      config: {
        systemInstruction,
        responseMimeType: "application/json",
      },
    });
    return parseJsonResponse<T>(response.text ?? "");
  }

  async generateFromImage({ prompt, systemInstruction, imageBase64, mimeType }: GemmaImageParams): Promise<string> {
    const response = await this.ai.models.generateContent({
      model: this.model,
      contents: [
        {
          role: "user",
          parts: [{ text: prompt }, { inlineData: { mimeType, data: imageBase64 } }],
        },
      ],
      config: systemInstruction ? { systemInstruction } : undefined,
    });
    return response.text ?? "";
  }
}

/**
 * Self-hosted Gemma 4 via any OpenAI-compatible chat completions endpoint
 * (Ollama `ollama serve`, vLLM `--api-key` server, etc). Swap to this by
 * setting GEMMA_PROVIDER=self_hosted — no application code changes needed.
 */
class SelfHostedGemmaClient implements GemmaClient {
  constructor(private readonly baseUrl: string, private readonly model: string) {}

  private async chat(messages: unknown[], jsonMode: boolean): Promise<string> {
    const res = await fetch(`${this.baseUrl}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: this.model,
        messages,
        ...(jsonMode ? { response_format: { type: "json_object" } } : {}),
      }),
    });
    if (!res.ok) {
      throw new Error(`Self-hosted Gemma 4 request failed: ${res.status} ${await res.text()}`);
    }
    const data = (await res.json()) as { choices: { message: { content: string } }[] };
    return data.choices[0]?.message?.content ?? "";
  }

  async generateText({ prompt, systemInstruction }: GemmaTextParams): Promise<string> {
    const messages = [
      ...(systemInstruction ? [{ role: "system", content: systemInstruction }] : []),
      { role: "user", content: prompt },
    ];
    return this.chat(messages, false);
  }

  async generateJson<T>({ prompt, systemInstruction, schemaDescription }: GemmaJsonParams): Promise<T> {
    const messages = [
      { role: "system", content: systemInstruction ?? "You are a JSON-only API." },
      { role: "user", content: `${prompt}\n\n${jsonInstruction(schemaDescription)}` },
    ];
    const raw = await this.chat(messages, true);
    return parseJsonResponse<T>(raw);
  }

  async generateFromImage({ prompt, systemInstruction, imageBase64, mimeType }: GemmaImageParams): Promise<string> {
    const messages = [
      ...(systemInstruction ? [{ role: "system", content: systemInstruction }] : []),
      {
        role: "user",
        content: [
          { type: "text", text: prompt },
          { type: "image_url", image_url: { url: `data:${mimeType};base64,${imageBase64}` } },
        ],
      },
    ];
    return this.chat(messages, false);
  }
}

let cachedClient: GemmaClient | undefined;

export function getGemmaClient(): GemmaClient {
  if (cachedClient) return cachedClient;

  if (env.gemma.provider === "self_hosted") {
    logger.info(`Gemma 4 provider: self-hosted at ${env.gemma.selfHostedUrl} (model=${env.gemma.model})`);
    cachedClient = new SelfHostedGemmaClient(env.gemma.selfHostedUrl, env.gemma.model);
  } else {
    if (!env.gemma.geminiApiKey) {
      throw new Error("GEMINI_API_KEY is required when GEMMA_PROVIDER=gemini_api");
    }
    logger.info(`Gemma 4 provider: Gemini API (model=${env.gemma.model})`);
    cachedClient = new GeminiApiGemmaClient(env.gemma.geminiApiKey, env.gemma.model);
  }

  return cachedClient;
}
