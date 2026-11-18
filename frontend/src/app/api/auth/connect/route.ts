import { NextRequest, NextResponse } from "next/server";
import type { TokenResponse, ConnectSafeResponse } from "@/types";
import { validateOriginAndCsrf } from "@/lib/server/csrf";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest): Promise<NextResponse> {
  // 1. Origin and CSRF validation to prevent Login-CSRF attacks
  const csrfCheck = validateOriginAndCsrf(request);
  if (!csrfCheck.valid) {
    return NextResponse.json(
      { detail: csrfCheck.reason || "Forbidden: Cross-origin request blocked." },
      {
        status: 403,
        headers: { "Cache-Control": "no-store, private" },
      }
    );
  }

  try {
    const body = await request.json().catch(() => null);

    if (!body || typeof body.api_key !== "string" || !body.api_key.trim()) {
      return NextResponse.json(
        { detail: "API key is required and must be a non-empty string." },
        {
          status: 400,
          headers: { "Cache-Control": "no-store, private" },
        }
      );
    }

    const apiKey = body.api_key.trim();

    // Call backend token exchange endpoint with timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    let backendRes: Response;
    try {
      backendRes = await fetch(`${BACKEND_URL}/api/v1/auth/token`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ api_key: apiKey }),
        cache: "no-store",
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeoutId);
    }

    const responseData = await backendRes.json().catch(() => ({}));

    if (!backendRes.ok) {
      return NextResponse.json(
        {
          detail:
            responseData.detail ??
            "Authentication failed. Please verify your agent API key.",
        },
        {
          status: backendRes.status,
          headers: { "Cache-Control": "no-store, private" },
        }
      );
    }

    const tokenData = responseData as TokenResponse;

    // Cookie expiry must NOT exceed backend token lifetime (maximum 1800s)
    const cookieMaxAge = Math.min(
      typeof tokenData.expires_in === "number" ? tokenData.expires_in : 1800,
      1800
    );

    // Build safe response body — explicitly omit the raw JWT access token from JSON
    const safeBody: ConnectSafeResponse = {
      success: true,
      agent_id: tokenData.agent_id,
      agent_name: tokenData.agent_name,
      company: tokenData.company,
      expires_in: cookieMaxAge,
    };

    const response = NextResponse.json(safeBody, {
      status: 200,
      headers: {
        "Cache-Control": "no-store, private",
      },
    });

    // Set HttpOnly, SameSite=Lax session cookie
    response.cookies.set("agent_session", tokenData.access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: cookieMaxAge,
    });

    return response;
  } catch (error: unknown) {
    console.error("Connect route error:", error);
    return NextResponse.json(
      { detail: "Internal connection error. Could not reach backend service." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store, private" },
      }
    );
  }
}
