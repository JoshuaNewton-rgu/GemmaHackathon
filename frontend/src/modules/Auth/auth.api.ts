import { httpClient } from "../../services/httpClient";
import type { User } from "../../types/api";

export interface AuthResponse {
  user: User;
  token: string;
}

export function register(email: string, password: string, name: string) {
  return httpClient.post<AuthResponse>("/auth/register", { email, password, name });
}

export function login(email: string, password: string) {
  return httpClient.post<AuthResponse>("/auth/login", { email, password });
}

export function fetchMe() {
  return httpClient.get<{ user: User }>("/auth/me");
}
