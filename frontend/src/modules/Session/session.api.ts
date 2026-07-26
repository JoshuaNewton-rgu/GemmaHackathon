import { httpClient } from "../../services/httpClient";
import type { NotesUploadResult, StudySession } from "../../types/api";
import type { PickedImage } from "../../components/UploadButton/UploadButton";

export function startSession(subject: string, plannedDurationMinutes: number) {
  return httpClient.post<{ session: StudySession }>("/sessions", { subject, plannedDurationMinutes });
}

export function abandonSession(sessionId: string) {
  return httpClient.post<{ session: StudySession }>(`/sessions/${sessionId}/abandon`);
}

export function listSessions() {
  return httpClient.get<{ sessions: StudySession[] }>("/sessions");
}

export function uploadNotes(sessionId: string, image: PickedImage) {
  const formData = new FormData();
  // React Native's FormData accepts this shape for file uploads (uri/name/type).
  formData.append("image", {
    uri: image.uri,
    name: image.fileName,
    type: image.mimeType,
  } as unknown as Blob);

  return httpClient.post<NotesUploadResult>(`/sessions/${sessionId}/notes`, formData);
}
