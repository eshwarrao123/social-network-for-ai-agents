import { NextRequest, NextResponse } from "next/server";
import type { AgentRegisterResponse } from "@/types";
import { validateOriginAndCsrf } from "@/lib/server/csrf";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest): Promise<NextResponse> {
  // 1. Origin and CSRF validation to prevent Registration-CSRF attacks
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

    if (!body || typeof body !== "object") {
      return NextResponse.json(
        { detail: "Registration payload is required." },
        {
          status: 400,
          headers: { "Cache-Control": "no-store, private" },
        }
      );
    }

    const { name, company, description, industries, capabilities, tags, webhook_url } = body;

    if (!name || typeof name !== "string" || !name.trim()) {
      return NextResponse.json(
        { detail: "Agent name is required." },
        {
          status: 400,
          headers: { "Cache-Control": "no-store, private" },
        }
      );
    }
    if (!company || typeof company !== "string" || !company.trim()) {
      return NextResponse.json(
        { detail: "Parent company name is required." },
        {
          status: 400,
          headers: { "Cache-Control": "no-store, private" },
        }
      );
    }
    if (!description || typeof description !== "string" || description.trim().length < 10) {
      return NextResponse.json(
        { detail: "Description manifesto must be at least 10 characters." },
        {
          status: 400,
          headers: { "Cache-Control": "no-store, private" },
        }
      );
    }
    if (!Array.isArray(industries) || industries.length === 0) {
      return NextResponse.json(
        { detail: "At least one industry vertical is required." },
        {
          status: 400,
          headers: { "Cache-Control": "no-store, private" },
        }
      );
    }

    const backendPayload = {
      name: name.trim(),
      company: company.trim(),
      description: description.trim(),
      industries,
      capabilities: Array.isArray(capabilities) ? capabilities : [],
      tags: Array.isArray(tags) ? tags : [],
      ...(webhook_url ? { webhook_url } : {}),
    };

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    let backendRes: Response;
    try {
      backendRes = await fetch(`${BACKEND_URL}/api/v1/agents/register`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(backendPayload),
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
            "Agent registration failed. Please check your inputs.",
        },
        {
          status: backendRes.status,
          headers: { "Cache-Control": "no-store, private" },
        }
      );
    }

    // Return the registration response with the raw API key for one-time display in transient UI state
    return NextResponse.json(responseData as AgentRegisterResponse, {
      status: 201,
      headers: {
        "Cache-Control": "no-store, private",
      },
    });
  } catch (error) {
    console.error("Register route error:", error);
    return NextResponse.json(
      { detail: "Internal registration error. Could not reach backend service." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store, private" },
      }
    );
  }
}
