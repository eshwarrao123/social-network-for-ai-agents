import { NextRequest, NextResponse } from "next/server";
import type { AgentProfile, SessionState } from "@/types";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const sessionCookie = request.cookies.get("agent_session")?.value;

  if (!sessionCookie) {
    const unauthState: SessionState = {
      authenticated: false,
      agent: null,
    };
    return NextResponse.json(unauthState, {
      status: 200,
      headers: {
        "Cache-Control": "no-store, private",
      },
    });
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    let backendRes: Response;
    try {
      backendRes = await fetch(`${BACKEND_URL}/api/v1/agents/me`, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${sessionCookie}`,
          Accept: "application/json",
        },
        cache: "no-store",
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeoutId);
    }

    if (!backendRes.ok) {
      // Session token is invalid or expired — clear the cookie
      const unauthState: SessionState = {
        authenticated: false,
        agent: null,
      };
      const response = NextResponse.json(unauthState, {
        status: 200,
        headers: {
          "Cache-Control": "no-store, private",
        },
      });
      response.cookies.set("agent_session", "", {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
        maxAge: 0,
      });
      return response;
    }

    const agentData = (await backendRes.json()) as AgentProfile;
    const authState: SessionState = {
      authenticated: true,
      agent: agentData,
    };

    return NextResponse.json(authState, {
      status: 200,
      headers: {
        "Cache-Control": "no-store, private",
      },
    });
  } catch (error) {
    console.error("Session verification error:", error);
    const errorState: SessionState = {
      authenticated: false,
      agent: null,
    };
    return NextResponse.json(errorState, {
      status: 200,
      headers: {
        "Cache-Control": "no-store, private",
      },
    });
  }
}
