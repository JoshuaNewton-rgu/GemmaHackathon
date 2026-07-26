import { Schema, model, Types, type InferSchemaType } from "mongoose";

export const COACH_MESSAGE_TYPES = ["praise", "roast", "break_granted", "break_denied"] as const;
export type CoachMessageType = (typeof COACH_MESSAGE_TYPES)[number];

const coachMessageSchema = new Schema(
  {
    userId: { type: Schema.Types.ObjectId, ref: "User", required: true, index: true },
    sessionId: { type: Schema.Types.ObjectId, ref: "Session", default: null },
    persona: { type: String, required: true },
    type: { type: String, enum: COACH_MESSAGE_TYPES, required: true },
    text: { type: String, required: true },
    audioUrl: { type: String, default: null },
    useDeviceTts: { type: Boolean, default: true },
  },
  { timestamps: true },
);

export type CoachMessageDoc = InferSchemaType<typeof coachMessageSchema> & { _id: Types.ObjectId };
export const CoachMessage = model("CoachMessage", coachMessageSchema);
