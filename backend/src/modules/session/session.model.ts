import { Schema, model, Types, type InferSchemaType } from "mongoose";

export const SESSION_STATUSES = ["active", "completed", "abandoned"] as const;
export type SessionStatus = (typeof SESSION_STATUSES)[number];

const sessionSchema = new Schema(
  {
    userId: { type: Schema.Types.ObjectId, ref: "User", required: true, index: true },
    subject: { type: String, required: true, trim: true },
    plannedDurationMinutes: { type: Number, required: true },
    startedAt: { type: Date, required: true, default: () => new Date() },
    endedAt: { type: Date, default: null },
    status: { type: String, enum: SESSION_STATUSES, default: "active" },
    progressScore: { type: Number, default: null },
    xpAwarded: { type: Number, default: 0 },
  },
  { timestamps: true },
);

export type SessionDoc = InferSchemaType<typeof sessionSchema> & { _id: Types.ObjectId };
export const Session = model("Session", sessionSchema);
