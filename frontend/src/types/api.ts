export type Persona = "scottish_granny" | "disappointed_mother" | "angry_father";

export interface Stats {
  focus: number;
  discipline: number;
  knowledge: number;
  consistency: number;
}

export interface Streak {
  current: number;
  longest: number;
  lastCompletedDate: string | null;
}

export interface User {
  id: string;
  email: string;
  name: string;
  persona: Persona;
  level: number;
  xp: number;
  stats: Stats;
  streak: Streak;
  achievements: string[];
}

export type SessionStatus = "active" | "completed" | "abandoned";

export interface StudySession {
  _id: string;
  userId: string;
  subject: string;
  plannedDurationMinutes: number;
  startedAt: string;
  endedAt: string | null;
  status: SessionStatus;
  progressScore: number | null;
  xpAwarded: number;
}

export type QuestionType = "definition" | "fill_blank" | "relationship";

export interface QuizQuestion {
  id: string;
  type: QuestionType;
  prompt: string;
  choices: string[];
}

export type QuizKind = "session" | "break";

export interface Quiz {
  id: string;
  kind: QuizKind;
  subject: string;
  submittedAt: string | null;
  questions: QuizQuestion[];
}

export interface GradedQuiz {
  _id: string;
  kind: QuizKind;
  correctCount: number;
  passed: boolean;
  questions: (QuizQuestion & { correctIndex: number; selectedIndex: number | null })[];
}

export interface ProgressBreakdown {
  score: number;
  volumeScore: number;
  newConceptsScore: number;
  completionScore: number;
  newKeywordCount: number;
  wordDelta: number;
}

export interface CoachMessage {
  _id: string;
  persona: Persona;
  type: "praise" | "roast" | "break_granted" | "break_denied";
  text: string;
  audioUrl: string | null;
  useDeviceTts: boolean;
}

export interface NotesUploadResult {
  session: StudySession;
  progressBreakdown: ProgressBreakdown;
  quiz: Quiz;
  coachMessage: CoachMessage;
  xpAwarded: number;
}

export interface BreakAnswerResult {
  quiz: GradedQuiz;
  passed: boolean;
  breakMinutes: number;
  coachMessage: CoachMessage;
  xpAwarded: number;
}
