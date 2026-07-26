export interface ProgressScoreInput {
  previousWordCount: number;
  currentWordCount: number;
  previousKeywords: string[];
  currentKeywords: string[];
  plannedDurationMinutes: number;
  actualDurationMinutes: number;
}

export interface ProgressScoreBreakdown {
  score: number;
  volumeScore: number;
  newConceptsScore: number;
  completionScore: number;
  newKeywordCount: number;
  wordDelta: number;
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

/**
 * 0-100 score combining: how much new note volume was written, how many
 * genuinely new concepts/keywords appeared, and whether the session ran
 * (close to) the full planned duration rather than being cut short.
 *
 * Weights: volume 40, new concepts 40, completion 20.
 */
export function computeProgressScore(input: ProgressScoreInput): ProgressScoreBreakdown {
  const wordDelta = Math.max(0, input.currentWordCount - input.previousWordCount);
  // Diminishing returns: +50 words -> ~half credit, +150 words -> full credit.
  const volumeScore = clamp((wordDelta / 150) * 40, 0, 40);

  const previousSet = new Set(input.previousKeywords.map((k) => k.toLowerCase().trim()));
  const newKeywords = input.currentKeywords.filter((k) => !previousSet.has(k.toLowerCase().trim()));
  const newKeywordCount = newKeywords.length;
  // 5+ genuinely new concepts in one session earns full credit.
  const newConceptsScore = clamp((newKeywordCount / 5) * 40, 0, 40);

  const completionRatio = input.plannedDurationMinutes > 0 ? input.actualDurationMinutes / input.plannedDurationMinutes : 0;
  const completionScore = clamp(completionRatio, 0, 1) * 20;

  const score = Math.round(volumeScore + newConceptsScore + completionScore);

  return {
    score: clamp(score, 0, 100),
    volumeScore: Math.round(volumeScore),
    newConceptsScore: Math.round(newConceptsScore),
    completionScore: Math.round(completionScore),
    newKeywordCount,
    wordDelta,
  };
}

/** XP earned immediately for uploading notes: base amount scaled by Progress Score. */
export function computeSessionXp(progressScore: number): number {
  const baseXp = 20;
  const progressBonus = Math.round((progressScore / 100) * 40);
  return baseXp + progressBonus;
}

/** Extra XP earned once a quiz (session recall quiz or break-gate quiz) is graded. */
export function computeQuizXp(correctCount: number, total: number): number {
  return total > 0 ? Math.round((correctCount / total) * 40) : 0;
}
