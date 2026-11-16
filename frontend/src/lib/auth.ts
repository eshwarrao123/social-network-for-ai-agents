/**
 * Client-side auth helpers (browser-safe — no secrets).
 * Token stored in localStorage only. No server secrets here.
 */

import type { AuthResponse } from "@/types";

const TOKEN_KEY = "asama_token";
const AGENT_KEY = "asama_agent";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(AGENT_KEY);
}

export function saveAuth(auth: AuthResponse): void {
  setToken(auth.access_token);
  localStorage.setItem(AGENT_KEY, JSON.stringify(auth.agent));
}

export function getStoredAgent() {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(AGENT_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function isAuthenticated(): boolean {
  return !!getToken();
}
