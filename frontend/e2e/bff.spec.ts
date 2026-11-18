import { test, expect } from "@playwright/test";
import { POST as handleConnect } from "../src/app/api/auth/connect/route";
import { POST as handleRegister } from "../src/app/api/auth/register/route";
import { GET as handleSession } from "../src/app/api/auth/session/route";
import { POST as handleDisconnect } from "../src/app/api/auth/disconnect/route";
import {
  GET as handleProxyGet,
  POST as handleProxyPost,
} from "../src/app/api/v1/[...path]/route";
import { NextRequest } from "next/server";

test.describe("BFF Auth & Security Unit/Integration Tests", () => {
  test("Connect: blocks cross-origin requests with 403 Forbidden (Login-CSRF protection)", async () => {
    const req = new NextRequest("http://localhost:3000/api/auth/connect", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        origin: "https://malicious-external-site.com",
      },
      body: JSON.stringify({ api_key: "asama_live_attacker_key" }),
    });

    const res = await handleConnect(req);
    expect(res.status).toBe(403);
    const data = await res.json();
    expect(data.detail).toContain("not a trusted application origin");
  });

  test("Connect: rejects requests with attacker-controlled Host header with 403 Forbidden", async () => {
    const req = new NextRequest("http://localhost:3000/api/auth/connect", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        origin: "https://evil.com",
        host: "evil.com",
      },
      body: JSON.stringify({ api_key: "asama_live_attacker_key" }),
    });

    const res = await handleConnect(req);
    expect(res.status).toBe(403);
  });

  test("Connect: rejects missing Origin and Referer on state-mutating request with 403", async () => {
    const req = new NextRequest("http://localhost:3000/api/auth/connect", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ api_key: "asama_live_some_key" }),
    });

    const res = await handleConnect(req);
    expect(res.status).toBe(403);
    const data = await res.json();
    expect(data.detail).toContain("Missing Origin and Referer");
  });

  test("Connect: rejects malformed Origin header with 403", async () => {
    const req = new NextRequest("http://localhost:3000/api/auth/connect", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        origin: "not-a-valid-url::80",
      },
      body: JSON.stringify({ api_key: "asama_live_some_key" }),
    });

    const res = await handleConnect(req);
    expect(res.status).toBe(403);
    const data = await res.json();
    expect(data.detail).toContain("Malformed Origin");
  });

  test("Connect: rejects missing or empty API key with 400 Bad Request on trusted same-origin request", async () => {
    const req = new NextRequest("http://localhost:3000/api/auth/connect", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        origin: "http://localhost:3000",
      },
      body: JSON.stringify({}),
    });

    const res = await handleConnect(req);
    expect(res.status).toBe(400);
    const data = await res.json();
    expect(data.detail).toContain("API key is required");
  });

  test("Connect: exchanges API key, sets HttpOnly cookie, bounds maxAge, and omits JWT from JSON", async () => {
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async (url, options) => {
        expect(String(url)).toContain("/api/v1/auth/token");
        const body = JSON.parse(String(options?.body));
        expect(body.api_key).toBe("asama_live_mockkey_987654321");

        return new Response(
          JSON.stringify({
            access_token: "mock_jwt_secret_token_header.payload.signature",
            token_type: "bearer",
            expires_in: 3600, // Backend returns 3600, but BFF must cap to <= 1800
            agent_id: "11111111-2222-3333-4444-555555555555",
            agent_name: "MockAgent-Alpha",
            company: "Apex Enterprise",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }
        );
      };

      const req = new NextRequest("http://localhost:3000/api/auth/connect", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          origin: "http://localhost:3000",
        },
        body: JSON.stringify({ api_key: "asama_live_mockkey_987654321" }),
      });

      const res = await handleConnect(req);
      expect(res.status).toBe(200);

      const data = await res.json();
      expect(data.success).toBe(true);
      expect(data.agent_name).toBe("MockAgent-Alpha");
      expect(data.company).toBe("Apex Enterprise");
      // Bounded maxAge
      expect(data.expires_in).toBe(1800);
      // Ensure access_token is NOT exposed in the JSON response
      expect(data.access_token).toBeUndefined();

      // Check cookie headers
      const cookieHeader = res.headers.get("set-cookie");
      expect(cookieHeader).toBeTruthy();
      expect(cookieHeader).toContain("agent_session=mock_jwt_secret_token");
      expect(cookieHeader?.toLowerCase()).toContain("httponly");
      expect(cookieHeader?.toLowerCase()).toContain("samesite=lax");
      expect(cookieHeader?.toLowerCase()).toContain("path=/");
      expect(cookieHeader).toContain("Max-Age=1800");

      // Check Cache-Control
      expect(res.headers.get("cache-control")).toBe("no-store, private");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("Register: blocks cross-origin requests with 403 Forbidden (Registration-CSRF)", async () => {
    const req = new NextRequest("http://localhost:3000/api/auth/register", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        origin: "https://evil.com",
      },
      body: JSON.stringify({ name: "EvilBot" }),
    });

    const res = await handleRegister(req);
    expect(res.status).toBe(403);
  });

  test("Register: forwards agent registration and returns one-time API key without setting cookie", async () => {
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async (url, options) => {
        expect(String(url)).toContain("/api/v1/agents/register");
        const body = JSON.parse(String(options?.body));
        expect(body.name).toBe("NewAgent-1");
        expect(body.company).toBe("Enterprise Co");

        return new Response(
          JSON.stringify({
            id: "22222222-3333-4444-5555-666666666666",
            name: "NewAgent-1",
            company: "Enterprise Co",
            description: "Interest manifesto operational description",
            industries: ["fintech", "banking"],
            capabilities: ["market-analysis"],
            tags: ["equities"],
            trust_score: 1.0,
            is_active: true,
            api_key: "asama_live_generatedkey12345",
            api_key_prefix: "asama_live_gene",
            created_at: new Date().toISOString(),
            message: "Registration successful.",
          }),
          {
            status: 201,
            headers: { "Content-Type": "application/json" },
          }
        );
      };

      const req = new NextRequest("http://localhost:3000/api/auth/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          origin: "http://localhost:3000",
        },
        body: JSON.stringify({
          name: "NewAgent-1",
          company: "Enterprise Co",
          description: "Interest manifesto operational description",
          industries: ["fintech", "banking"],
          capabilities: ["market-analysis"],
          tags: ["equities"],
        }),
      });

      const res = await handleRegister(req);
      expect(res.status).toBe(201);
      const data = await res.json();
      expect(data.api_key).toBe("asama_live_generatedkey12345");
      expect(data.name).toBe("NewAgent-1");

      const cookieHeader = res.headers.get("set-cookie");
      expect(cookieHeader).toBeNull();
      expect(res.headers.get("cache-control")).toBe("no-store, private");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("Disconnect: blocks cross-origin requests with 403 Forbidden (Logout-CSRF)", async () => {
    const req = new NextRequest("http://localhost:3000/api/auth/disconnect", {
      method: "POST",
      headers: {
        origin: "https://evil.com",
      },
    });

    const res = await handleDisconnect(req);
    expect(res.status).toBe(403);
  });

  test("Disconnect: expires agent_session cookie with maxAge=0 on same-origin request", async () => {
    const req = new NextRequest("http://localhost:3000/api/auth/disconnect", {
      method: "POST",
      headers: {
        origin: "http://localhost:3000",
      },
    });

    const res = await handleDisconnect(req);
    expect(res.status).toBe(200);

    const cookieHeader = res.headers.get("set-cookie");
    expect(cookieHeader).toBeTruthy();
    expect(cookieHeader).toContain("agent_session=;");
    expect(cookieHeader).toContain("Max-Age=0");
    expect(res.headers.get("cache-control")).toBe("no-store, private");
  });

  test("Session: returns authenticated=false when cookie is missing", async () => {
    const req = new NextRequest("http://localhost:3000/api/auth/session");
    const res = await handleSession(req);
    expect(res.status).toBe(200);

    const data = await res.json();
    expect(data.authenticated).toBe(false);
    expect(data.agent).toBeNull();
    expect(res.headers.get("cache-control")).toBe("no-store, private");
  });

  test("Session: queries backend and returns authenticated profile with valid cookie", async () => {
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async (url, options) => {
        expect(String(url)).toContain("/api/v1/agents/me");
        expect((options?.headers as Record<string, string>)?.Authorization).toBe("Bearer valid_jwt_token_xyz");

        return new Response(
          JSON.stringify({
            id: "33333333-4444-5555-6666-777777777777",
            name: "VerifiedAgent",
            company: "ApexFin",
            description: "Agent manifesto",
            industries: ["fintech"],
            capabilities: [],
            tags: [],
            trust_score: 0.95,
            is_active: true,
            api_key_prefix: "asama_live_veri",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      };

      const req = new NextRequest("http://localhost:3000/api/auth/session", {
        headers: {
          cookie: "agent_session=valid_jwt_token_xyz",
        },
      });

      const res = await handleSession(req);
      expect(res.status).toBe(200);
      const data = await res.json();
      expect(data.authenticated).toBe(true);
      expect(data.agent.name).toBe("VerifiedAgent");
      expect(res.headers.get("cache-control")).toBe("no-store, private");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("Session: clears cookie and returns authenticated=false when backend returns 401", async () => {
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async () => {
        return new Response(JSON.stringify({ detail: "Token has expired" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      };

      const req = new NextRequest("http://localhost:3000/api/auth/session", {
        headers: {
          cookie: "agent_session=expired_jwt_token",
        },
      });

      const res = await handleSession(req);
      expect(res.status).toBe(200);
      const data = await res.json();
      expect(data.authenticated).toBe(false);
      expect(data.agent).toBeNull();

      const cookieHeader = res.headers.get("set-cookie");
      expect(cookieHeader).toBeTruthy();
      expect(cookieHeader).toContain("Max-Age=0");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("BFF Proxy: rejects unauthenticated requests with 401 Unauthorized", async () => {
    const req = new NextRequest("http://localhost:3000/api/v1/agents/me");
    const res = await handleProxyGet(req, {
      params: Promise.resolve({ path: ["agents", "me"] }),
    });

    expect(res.status).toBe(401);
    const data = await res.json();
    expect(data.detail).toContain("Authentication required");
  });

  test("BFF Proxy: blocks CSRF cross-origin mutations with 403 Forbidden", async () => {
    const req = new NextRequest("http://localhost:3000/api/v1/posts", {
      method: "POST",
      headers: {
        cookie: "agent_session=valid_jwt",
        origin: "https://evil-cross-site.com",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ title: "Cross-Site Attack" }),
    });

    const res = await handleProxyPost(req, {
      params: Promise.resolve({ path: ["posts"] }),
    });

    expect(res.status).toBe(403);
    const data = await res.json();
    expect(data.detail).toContain("not a trusted application origin");
  });

  test("BFF Proxy: rejects path traversal attempts with 400 Bad Request", async () => {
    const req = new NextRequest("http://localhost:3000/api/v1/..%2f..%2fadmin", {
      headers: {
        cookie: "agent_session=valid_jwt",
      },
    });

    const res = await handleProxyGet(req, {
      params: Promise.resolve({ path: ["..", "admin"] }),
    });

    expect(res.status).toBe(400);
    const data = await res.json();
    expect(data.detail).toContain("traversal");
  });

  test("BFF Proxy: strips client Authorization and Cookie headers and does not leak upstream Set-Cookie", async () => {
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async (url, options) => {
        expect(String(url)).toContain("/api/v1/agents/me");
        // Server's session token MUST be injected, NOT client's spoofed Authorization header
        const headers = options?.headers as Record<string, string> | undefined;
        expect(headers?.Authorization).toBe("Bearer server_cookie_token");
        expect(headers?.Cookie).toBeUndefined();

        return new Response(JSON.stringify({ id: "agent-123" }), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Set-Cookie": "backend_secret=12345; HttpOnly",
          },
        });
      };

      const req = new NextRequest("http://localhost:3000/api/v1/agents/me", {
        headers: {
          cookie: "agent_session=server_cookie_token",
          authorization: "Bearer attacker_spoofed_token",
        },
      });

      const res = await handleProxyGet(req, {
        params: Promise.resolve({ path: ["agents", "me"] }),
      });

      expect(res.status).toBe(200);
      expect(res.headers.get("cache-control")).toBe("no-store, private");

      // Verify upstream Set-Cookie was stripped
      const clientCookie = res.headers.get("set-cookie");
      expect(clientCookie).toBeNull();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("BFF Proxy: clears session cookie if upstream backend returns 401 Unauthorized", async () => {
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async () => {
        return new Response(JSON.stringify({ detail: "Token invalid or revoked" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      };

      const req = new NextRequest("http://localhost:3000/api/v1/posts", {
        headers: {
          cookie: "agent_session=invalid_jwt_token",
        },
      });

      const res = await handleProxyGet(req, {
        params: Promise.resolve({ path: ["posts"] }),
      });

      expect(res.status).toBe(401);
      const cookieHeader = res.headers.get("set-cookie");
      expect(cookieHeader).toBeTruthy();
      expect(cookieHeader).toContain("Max-Age=0");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
