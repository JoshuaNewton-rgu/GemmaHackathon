import { httpClient } from "../../services/httpClient";
import type { BreakAnswerResult, Quiz } from "../../types/api";

export function generateBreakQuiz(subject: string) {
  return httpClient.post<{ quiz: Quiz }>("/quiz/break", { subject });
}

export function submitBreakAnswers(quizId: string, answers: { questionId: string; selectedIndex: number }[]) {
  return httpClient.post<BreakAnswerResult>(`/quiz/${quizId}/answers`, { answers });
}
