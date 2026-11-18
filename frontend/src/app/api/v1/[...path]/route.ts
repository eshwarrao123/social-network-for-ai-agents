import { NextRequest, NextResponse } from "next/server";
import { validateOriginAndCsrf } from "@/lib/server/csrf";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

const FORBIDDEN_PATH_CHARS = /[\\]|(%2e|%2f|%5c|\.\.)/i;

function isValidPathSegment(segment: string): boolean {
  if (!segment || segment.trim().length === 0) return false;
  if (segment === "." || segment === "..") return false;
  if (FORBIDDEN_PATH_CHARS.test(segment)) return false;
  return true;
}

async function proxyRequest(
  request: NextRequest,
  context: RouteContext,
  method: string
): Promise<NextResponse> {
  const { path } = await context.params;

  // 1. Path traversal and malformed segment validation
  if (!Array.isArray(path) || path.length === 0) {
    return NextResponse.json(
      { detail: "Invalid request path." },
      {
        status: 400,
        headers: { "Cache-Control": "no-store, private" },
      }
    );
  }

  for (const segment of path) {
    if (!isValidPathSegment(segment)) {
      return NextResponse.json(
        { detail: "Invalid or malicious path traversal segment detected." },
        {
          status: 400,
          headers: { "Cache-Control": "no-store, private" },
        }
      );
    }
  }

  const encodedPath = path.map((s) => encodeURIComponent(s)).join("/");
  const search = request.nextUrl.search;

  // 2. Session boundary check: read HttpOnly cookie
  const sessionToken = request.cookies.get("agent_session")?.value;
  if (!sessionToken) {
    return NextResponse.json(
      { detail: "Authentication required. Please connect your agent workspace." },
      {
        status: 401,
        headers: { "Cache-Control": "no-store, private" },
      }
    );
  }

  // 3. CSRF / Origin check on state-mutating methods
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
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
  }

  // 4. Build upstream URL strictly from trusted BACKEND_URL configuration
  const upstreamUrl = `${BACKEND_URL}/api/v1/${encodedPath}${search}`;

  // 5. Header filtering: strip hop-by-hop & browser credential headers; forward only safe headers
  const upstreamHeaders: Record<string, string> = {
    Authorization: `Bearer ${sessionToken}`,
    Accept: "application/json",
  };

  const allowedForwardHeaders = [
    "content-type",
    "idempotency-key",
    "x-idempotency-key",
  ];

  for (const headerName of allowedForwardHeaders) {
    const val = request.headers.get(headerName);
    if (val) {
      upstreamHeaders[headerName] = val;
    }
  }

  let body: BodyInit | undefined = undefined;
  if (["POST", "PUT", "PATCH"].includes(method)) {
    try {
      body = await request.text();
    } catch {
      body = undefined;
    }
  }

  // 6. Request timeout & dispatch
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);

  try {
    const upstreamRes = await fetch(upstreamUrl, {
      method,
      headers: upstreamHeaders,
      body,
      cache: "no-store",
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    const upstreamStatus = upstreamRes.status;
    const responseHeaders = new Headers();
    responseHeaders.set("Cache-Control", "no-store, private");

    // Copy Content-Type if present
    const upstreamContentType = upstreamRes.headers.get("content-type");
    if (upstreamContentType) {
      responseHeaders.set("Content-Type", upstreamContentType);
    }

    // Never leak upstream Set-Cookie headers
    // (responseHeaders does NOT copy set-cookie from upstream)

    // Handle 204 No Content
    if (upstreamStatus === 204) {
      return new NextResponse(null, {
        status: 204,
        headers: responseHeaders,
      });
    }

    const responseBody = await upstreamRes.arrayBuffer();
    const response = new NextResponse(responseBody, {
      status: upstreamStatus,
      headers: responseHeaders,
    });

    // If upstream returns 401 Unauthorized (e.g. token expired), clear session cookie
    if (upstreamStatus === 401) {
      response.cookies.set("agent_session", "", {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
        maxAge: 0,
      });
    }

    return response;
  } catch (error: unknown) {
    clearTimeout(timeoutId);
    console.error(`BFF Proxy [${method} ${encodedPath}] error:`, error);
    return NextResponse.json(
      { detail: "Backend communication error or upstream service timeout." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store, private" },
      }
    );
  }
}

export async function GET(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxyRequest(request, context, "GET");
}

export async function POST(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxyRequest(request, context, "POST");
}

export async function PUT(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxyRequest(request, context, "PUT");
}

export async function PATCH(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxyRequest(request, context, "PATCH");
}

export async function DELETE(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxyRequest(request, context, "DELETE");
}
