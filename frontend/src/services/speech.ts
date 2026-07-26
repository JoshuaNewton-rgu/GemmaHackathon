import * as Speech from "expo-speech";
import type { Persona } from "../types/api";

// Rough per-persona voice tuning for the default on-device TTS provider.
// Swap for real persona voices once the backend TTS provider is set to
// "elevenlabs" and `audioUrl` starts coming back from the API instead.
const PERSONA_VOICE_TUNING: Record<Persona, Speech.SpeechOptions> = {
  scottish_granny: { pitch: 1.1, rate: 0.9 },
  disappointed_mother: { pitch: 1.0, rate: 0.85 },
  angry_father: { pitch: 0.8, rate: 1.05 },
};

export function speakCoachLine(text: string, persona: Persona): void {
  Speech.stop();
  Speech.speak(text, PERSONA_VOICE_TUNING[persona]);
}

export function stopSpeaking(): void {
  Speech.stop();
}
