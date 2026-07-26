import { httpClient } from "../../services/httpClient";
import type { GradedQuiz, StudySession } from "../../types/api";

export function listSessions() {
  return httpClient.get<{ sessions: StudySession[] }>("/sessions");
}

export function listQuizzes() {
  return httpClient.get<{ quizzes: GradedQuiz[] }>("/quiz");
}
