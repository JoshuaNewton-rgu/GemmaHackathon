import { env } from "./env.js";
import { logger } from "../utils/logger.js";

export interface TtsResult {
  /** True when the client should speak `text` itself (Expo Speech / Web Speech API). */
  useDeviceTts: boolean;
  /** Populated only when a server-side voice provider generated real audio. */
  audioUrl?: string;
}

export interface TtsProvider {
  synthesize(text: string, personaVoiceId: string): Promise<TtsResult>;
}

/** Zero-cost, zero-API-key default: the client speaks the coach line itself. */
class DeviceTtsProvider implements TtsProvider {
  async synthesize(): Promise<TtsResult> {
    return { useDeviceTts: true };
  }
}

/**
 * Stub for a real persona-voice provider (e.g. ElevenLabs). Wire up the
 * actual HTTP call here once an API key + voice IDs per persona are chosen;
 * everything upstream (coach.service.ts) already treats `audioUrl` as
 * opaque, so no other code needs to change.
 */
class ElevenLabsTtsProvider implements TtsProvider {
  constructor(private readonly apiKey: string) {}

  async synthesize(text: string, personaVoiceId: string): Promise<TtsResult> {
    logger.warn(
      "ElevenLabsTtsProvider.synthesize is a stub - falling back to device TTS. " +
        "Implement the ElevenLabs call here (POST /v1/text-to-speech/{voice_id}) and " +
        "return { useDeviceTts: false, audioUrl } once ready.",
    );
    void text;
    void personaVoiceId;
    void this.apiKey;
    return { useDeviceTts: true };
  }
}

let cachedProvider: TtsProvider | undefined;

export function getTtsProvider(): TtsProvider {
  if (cachedProvider) return cachedProvider;

  if (env.tts.provider === "elevenlabs" && env.tts.elevenLabsApiKey) {
    cachedProvider = new ElevenLabsTtsProvider(env.tts.elevenLabsApiKey);
  } else {
    cachedProvider = new DeviceTtsProvider();
  }

  return cachedProvider;
}
