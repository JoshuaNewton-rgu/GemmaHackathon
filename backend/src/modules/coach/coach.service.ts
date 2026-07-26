import { getGemmaClient } from "../../config/gemma.js";
import { getTtsProvider } from "../../config/tts.js";
import type { Persona } from "../auth/auth.model.js";
import { CoachMessage, type CoachMessageType } from "./coach.model.js";

const PERSONA_STYLE: Record<Persona, string> = {
  scottish_granny:
    "You are a warm but blunt Scottish granny. Use gentle Scots flavour ('hen', 'wee', 'away and...') " +
    "sparingly. You genuinely care and want them to do well, but you don't sugarcoat laziness.",
  disappointed_mother:
    "You are a mother who is quietly disappointed rather than angry. Soft guilt, lots of care, " +
    "sighs implied through word choice ('I just... I thought you were better than this, love.').",
  angry_father:
    "You are a strict but fair father. Harsh, no-nonsense, raises his voice through capitalisation " +
    "sparingly, but always ends by making clear he believes they can do better.",
};

const PERSONA_VOICE_ID: Record<Persona, string> = {
  scottish_granny: "voice-scottish-granny",
  disappointed_mother: "voice-disappointed-mother",
  angry_father: "voice-angry-father",
};

async function generateLine(persona: Persona, type: CoachMessageType, contextSummary: string): Promise<string> {
  const gemma = getGemmaClient();
  const text = await gemma.generateText({
    systemInstruction:
      `${PERSONA_STYLE[persona]} Reply with ONE short in-character line (max 2 sentences, no stage directions, no quotation marks).`,
    prompt: `Situation: ${contextSummary}\n\nGive your reaction as this character.`,
  });
  return text.trim().replace(/^"|"$/g, "");
}

export async function createCoachMessage(params: {
  userId: string;
  sessionId?: string;
  persona: Persona;
  type: CoachMessageType;
  contextSummary: string;
}) {
  const text = await generateLine(params.persona, params.type, params.contextSummary);
  const tts = await getTtsProvider().synthesize(text, PERSONA_VOICE_ID[params.persona]);

  return CoachMessage.create({
    userId: params.userId,
    sessionId: params.sessionId ?? null,
    persona: params.persona,
    type: params.type,
    text,
    audioUrl: tts.audioUrl ?? null,
    useDeviceTts: tts.useDeviceTts,
  });
}

export function summarizeSessionOutcome(progressScore: number): { type: CoachMessageType; summary: string } {
  if (progressScore >= 70) {
    return {
      type: "praise",
      summary: `The student just finished a study session and scored ${progressScore}/100 on their Progress Score (based on new notes written and new concepts covered). Praise them.`,
    };
  }
  return {
    type: "roast",
    summary: `The student just finished a study session but only scored ${progressScore}/100 on their Progress Score - barely any new notes or new concepts. Call them out (kindly, in character).`,
  };
}

export function summarizeBreakOutcome(passed: boolean, correctCount: number, total: number): { type: CoachMessageType; summary: string } {
  if (passed) {
    return {
      type: "break_granted",
      summary: `The student answered ${correctCount}/${total} correctly on their break quiz (their own notes) and earned their break.`,
    };
  }
  return {
    type: "break_denied",
    summary: `The student only answered ${correctCount}/${total} correctly on their break quiz (their own notes) - not enough to earn a break. They need to go re-read.`,
  };
}
