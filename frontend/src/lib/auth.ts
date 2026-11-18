"use client";

import useSWR, { mutate as globalMutate } from "swr";
import { useEffect } from "react";
import type {
  AgentRegisterRequest,
  AgentRegisterResponse,
  ConnectSafeResponse,
  SessionState,
} from "@/types";
import { ApiError } from "./api";

/**
 * Connect an existing enterprise agent using its private API key.
 * Exchanging the key for an HttpOnly session cookie via BFF route.
 * Raw API key is never stored in browser localStorage or sessionStorage.
 */
export async function connectAgent(apiKey: string): Promise<ConnectSafeResponse> {
  const res = await fetch("/api/auth/connect", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ api_key: apiKey }),
    credentials: "same-origin",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      errorData?.detail ?? "Failed to connect agent workspace.",
      errorData
    );
  }

  const data = (await res.json()) as ConnectSafeResponse;

  // Clear any existing SWR cache entries from a previous session to ensure tenant cache isolation
  await globalMutate(() => true, undefined, { revalidate: false });
  // Revalidate session state across all components
  await globalMutate("/api/auth/session");

  return data;
}

/**
 * Register a new enterprise agent profile.
 * Returns the registration response containing the one-time raw API key.
 * This key is kept ONLY in transient component memory for one-time display.
 */
export async function registerAgent(
  payload: AgentRegisterRequest
): Promise<AgentRegisterResponse> {
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
    credentials: "same-origin",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      errorData?.detail ?? "Agent registration failed.",
      errorData
    );
  }

  return (await res.json()) as AgentRegisterResponse;
}

/**
 * Disconnect current agent workspace.
 * Clears HttpOnly session cookie and resets all cached queries.
 * Note: Since backend JWT is stateless, browser disconnect invalidates the
 * local session cookie and cached state, but does not revoke the backend token.
 */
export async function disconnectAgent(): Promise<void> {
  try {
    await fetch("/api/auth/disconnect", {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
      credentials: "same-origin",
    });
  } catch (err) {
    console.error("Disconnect error:", err);
  } finally {
    // Purge all SWR cache entries to ensure tenant isolation
    await globalMutate(() => true, undefined, { revalidate: false });
    // Reset session cache
    await globalMutate(
      "/api/auth/session",
      { authenticated: false, agent: null },
      false
    );
    if (typeof window !== "undefined") {
      window.location.href = "/connect";
    }
  }
}

const sessionFetcher = async (url: string): Promise<SessionState> => {
  const res = await fetch(url, { credentials: "same-origin", cache: "no-store" });
  if (!res.ok) {
    return { authenticated: false, agent: null };
  }
  return res.json();
};

/**
 * React hook for inspecting and reacting to the authenticated agent session.
 */
export function useSession() {
  const { data, error, isLoading, mutate } = useSWR<SessionState>(
    "/api/auth/session",
    sessionFetcher,
    {
      revalidateOnFocus: true,
      dedupingInterval: 10000,
      fallbackData: { authenticated: false, agent: null },
    }
  );

  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleExpired = () => {
      // Clear cache and redirect
      globalMutate(() => true, undefined, { revalidate: false });
      mutate({ authenticated: false, agent: null }, false);
      window.location.href = "/connect?expired=true";
    };

    window.addEventListener("agent-session-expired", handleExpired);
    return () => {
      window.removeEventListener("agent-session-expired", handleExpired);
    };
  }, [mutate]);

  return {
    session: data,
    agent: data?.agent ?? null,
    isAuthenticated: Boolean(data?.authenticated && data?.agent),
    isLoading,
    isError: error,
    mutate,
  };
}
