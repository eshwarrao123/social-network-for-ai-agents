import { NextRequest, NextResponse } from "next/server";
import { validateOriginAndCsrf } from "@/lib/server/csrf";

export async function POST(request: NextRequest): Promise<NextResponse> {
  // 1. Origin and CSRF validation to prevent Disconnect-CSRF (DoS)
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

  const response = NextResponse.json(
    { success: true, message: "Workspace disconnected successfully." },
    {
      status: 200,
      headers: {
        "Cache-Control": "no-store, private",
      },
    }
  );

  // Clear the browser HttpOnly session cookie
  response.cookies.set("agent_session", "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });

  return response;
}
