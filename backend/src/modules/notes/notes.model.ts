import { Schema, model, Types, type InferSchemaType } from "mongoose";

const noteSnapshotSchema = new Schema(
  {
    sessionId: { type: Schema.Types.ObjectId, ref: "Session", required: true, index: true },
    userId: { type: Schema.Types.ObjectId, ref: "User", required: true, index: true },
    subject: { type: String, required: true },
    imageUrl: { type: String, required: true },
    ocrText: { type: String, required: true },
    headings: { type: [String], default: [] },
    keywords: { type: [String], default: [] },
    wordCount: { type: Number, required: true },
  },
  { timestamps: true },
);

export type NoteSnapshotDoc = InferSchemaType<typeof noteSnapshotSchema> & { _id: Types.ObjectId };
export const NoteSnapshot = model("NoteSnapshot", noteSnapshotSchema);
