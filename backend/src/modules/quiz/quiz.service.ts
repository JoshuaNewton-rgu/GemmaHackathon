import { randomUUID } from "node:crypto";
import { getGemmaClient } from "../../config/gemma.js";
import { HttpError } from "../../middleware/errorHandler.js";
import { Quiz, type QuestionType, type QuizKind } from "./quiz.model.js";

interface GeneratedQuestion {
  type: QuestionType;
  prompt: string;
  choices: string[];
  correctIndex: number;
}

function difficultyLabel(userLevel: number): string {
  if (userLevel < 3) return "easy: direct recall of a single fact or definition from the notes";
  if (userLevel < 7) return "medium: recall plus applying a term correctly in context";
  return "hard: combine two or more concepts from the notes to answer (why X relates to Y)";
}

async function generateQuestions(noteText: string, count: number, userLevel: number): Promise<GeneratedQuestion[]> {
  if (!noteText.trim()) {
    throw new HttpError(400, "No note text available to generate a quiz from yet");
  }

  const gemma = getGemmaClient();
  const { questions } = await gemma.generateJson<{ questions: GeneratedQuestion[] }>({
    systemInstruction:
      "You write short recall quizzes for a student from their own handwritten notes. " +
      "Questions must be answerable ONLY from the provided notes text - never invent facts.",
    prompt:
      `Notes:\n"""${noteText}"""\n\n` +
      `Write exactly ${count} multiple-choice questions at this difficulty: ${difficultyLabel(userLevel)}. ` +
      'Mix question "type" across: "definition" (what is X), "fill_blank" (fill in the missing term), ' +
      'and "relationship" (why/how X relates to Y). Each question needs exactly 4 choices with exactly one correct answer.',
    schemaDescription:
      '{ "questions": [{ "type": "definition"|"fill_blank"|"relationship", "prompt": string, ' +
      '"choices": string[4], "correctIndex": 0|1|2|3 }] }',
  });

  if (!Array.isArray(questions) || questions.length === 0) {
    throw new HttpError(502, "Gemma 4 did not return any quiz questions");
  }

  return questions;
}

export async function createQuiz(params: {
  userId: string;
  sessionId: string | null;
  subject: string;
  kind: QuizKind;
  noteText: string;
  userLevel: number;
  questionCount: number;
}) {
  const generated = await generateQuestions(params.noteText, params.questionCount, params.userLevel);

  return Quiz.create({
    userId: params.userId,
    sessionId: params.sessionId,
    kind: params.kind,
    subject: params.subject,
    questions: generated.map((q) => ({ ...q, id: randomUUID(), selectedIndex: null })),
  });
}

export function toPublicQuiz(quiz: { id: string; kind: string; subject: string; submittedAt: Date | null; questions: { id: string; type: string; prompt: string; choices: string[] }[] }) {
  return {
    id: quiz.id,
    kind: quiz.kind,
    subject: quiz.subject,
    submittedAt: quiz.submittedAt,
    questions: quiz.questions.map((q) => ({ id: q.id, type: q.type, prompt: q.prompt, choices: q.choices })),
  };
}

export async function gradeQuiz(userId: string, quizId: string, answers: { questionId: string; selectedIndex: number }[]) {
  const quiz = await Quiz.findOne({ _id: quizId, userId });
  if (!quiz) throw new HttpError(404, "Quiz not found");
  if (quiz.submittedAt) throw new HttpError(409, "Quiz already submitted");

  const answerMap = new Map(answers.map((a) => [a.questionId, a.selectedIndex]));
  let correctCount = 0;

  for (const question of quiz.questions) {
    const selected = answerMap.get(question.id) ?? null;
    question.selectedIndex = selected;
    if (selected === question.correctIndex) correctCount += 1;
  }

  quiz.correctCount = correctCount;
  quiz.submittedAt = new Date();
  quiz.passed = correctCount / quiz.questions.length >= 0.6; // >= 3/5
  await quiz.save();

  return quiz;
}
