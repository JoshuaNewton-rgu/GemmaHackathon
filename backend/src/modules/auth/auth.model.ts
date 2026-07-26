import { Schema, model, type InferSchemaType } from "mongoose";

export const PERSONAS = ["scottish_granny", "disappointed_mother", "angry_father"] as const;
export type Persona = (typeof PERSONAS)[number];

const statsSchema = new Schema(
  {
    focus: { type: Number, default: 0 },
    discipline: { type: Number, default: 0 },
    knowledge: { type: Number, default: 0 },
    consistency: { type: Number, default: 0 },
  },
  { _id: false },
);

const streakSchema = new Schema(
  {
    current: { type: Number, default: 0 },
    longest: { type: Number, default: 0 },
    lastCompletedDate: { type: String, default: null }, // YYYY-MM-DD, keeps timezone math out of the schema
  },
  { _id: false },
);

const achievementProgressSchema = new Schema(
  {
    highProgressSessions: { type: Number, default: 0 }, // toward "Proof machine"
    highScoreBreaksEarned: { type: Number, default: 0 }, // toward "Boss crusher"
  },
  { _id: false },
);

const userSchema = new Schema(
  {
    email: { type: String, required: true, unique: true, lowercase: true, trim: true },
    passwordHash: { type: String, required: true },
    name: { type: String, required: true, trim: true },
    persona: { type: String, enum: PERSONAS, default: "scottish_granny" },
    level: { type: Number, default: 1 },
    xp: { type: Number, default: 0 },
    stats: { type: statsSchema, default: () => ({}) },
    streak: { type: streakSchema, default: () => ({}) },
    achievements: { type: [String], default: [] },
    achievementProgress: { type: achievementProgressSchema, default: () => ({}) },
  },
  { timestamps: true },
);

export type UserDoc = InferSchemaType<typeof userSchema>;
export const User = model("User", userSchema);
