import { httpClient } from "./httpClient";
import type { GradedQuiz } from "../types/api";

/** Shared by the post-session recall quiz (Session module) and the break-gate quiz (Break module). */
export function submitQuizAnswers(quizId: string, answers: { questionId: string; selectedIndex: number }[]) {
  return httpClient.post<{ quiz: GradedQuiz; xpAwarded: number }>(`/quiz/${quizId}/answers`, { answers });
}
