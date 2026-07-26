import { Schema, model, Types, type InferSchemaType } from "mongoose";

export const QUIZ_KINDS = ["session", "break"] as const;
export type QuizKind = (typeof QUIZ_KINDS)[number];

export const QUESTION_TYPES = ["definition", "fill_blank", "relationship"] as const;
export type QuestionType = (typeof QUESTION_TYPES)[number];

const questionSchema = new Schema(
  {
    id: { type: String, required: true },
    type: { type: String, enum: QUESTION_TYPES, required: true },
    prompt: { type: String, required: true },
    choices: { type: [String], required: true },
    correctIndex: { type: Number, required: true },
    selectedIndex: { type: Number, default: null },
  },
  { _id: false },
);

const quizSchema = new Schema(
  {
    userId: { type: Schema.Types.ObjectId, ref: "User", required: true, index: true },
    // Required for "session" quizzes; for "break" quizzes it references the most recent
    // completed session for the subject (break requests aren't tied to one session).
    sessionId: { type: Schema.Types.ObjectId, ref: "Session", default: null, index: true },
    kind: { type: String, enum: QUIZ_KINDS, required: true },
    subject: { type: String, required: true },
    questions: { type: [questionSchema], required: true },
    correctCount: { type: Number, default: null },
    passed: { type: Boolean, default: null },
    submittedAt: { type: Date, default: null },
  },
  { timestamps: true },
);

export type QuizDoc = InferSchemaType<typeof quizSchema> & { _id: Types.ObjectId };
export const Quiz = model("Quiz", quizSchema);
