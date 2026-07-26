import { httpClient } from "../../services/httpClient";
import type { Persona, User } from "../../types/api";

export function updatePersona(persona: Persona) {
  return httpClient.patch<{ user: User }>("/auth/persona", { persona });
}
