import { NextRequest } from "next/server";

/**
 * Validates request Origin and Referer headers against trusted origins.
 * Mitigates CSRF, Login-CSRF, Registration-CSRF, Disconnect-CSRF,
 * and Host-header injection attacks.
 */

export function getTrustedOrigins(): Set<string> {
  const trusted = new Set<string>();

  // 1. Explicit configured trusted origins from server environment
  const envOrigins =
    process.env.TRUSTED_ORIGINS ||
    process.env.APP_URL ||
    process.env.NEXTAUTH_URL;

  if (envOrigins) {
    for (const origin of envOrigins.split(",")) {
      const trimmed = origin.trim();
      if (trimmed) {
        try {
          const u = new URL(trimmed);
          trusted.add(u.origin.toLowerCase());
        } catch {
          // ignore invalid env configuration
        }
      }
    }
  }

  // 2. Default trusted local application origins (fallback for local dev & production verification)
  trusted.add("http://localhost:3000");
  trusted.add("http://127.0.0.1:3000");

  return trusted;
}

export function isDevAllowedOrigin(originStr: string): boolean {
  if (process.env.NODE_ENV === "production") return false;
  try {
    const u = new URL(originStr);
    const host = u.hostname.toLowerCase();
    return (
      (host === "localhost" || host === "127.0.0.1") &&
      (u.protocol === "http:" || u.protocol === "https:")
    );
  } catch {
    return false;
  }
}

export interface CsrfValidationResult {
  valid: boolean;
  reason?: string;
}

export function validateOriginAndCsrf(request: NextRequest): CsrfValidationResult {
  // Check Sec-Fetch-Site if provided by modern browsers
  const secFetchSite = request.headers.get("sec-fetch-site");
  if (secFetchSite && secFetchSite === "cross-site") {
    return {
      valid: false,
      reason: "Cross-site request blocked by Sec-Fetch-Site policy.",
    };
  }

  const originHeader = request.headers.get("origin");
  const refererHeader = request.headers.get("referer");

  // On state-mutating requests, browsers provide Origin or Referer.
  // Missing both on a state-mutating browser request indicates an untrusted source.
  if (!originHeader && !refererHeader) {
    return {
      valid: false,
      reason: "Missing Origin and Referer headers on state-mutating request.",
    };
  }

  let requestOrigin: string | null = null;

  if (originHeader) {
    try {
      const u = new URL(originHeader);
      if (u.origin === "null") {
        return { valid: false, reason: "Malformed Origin header (opaque origin)." };
      }
      requestOrigin = u.origin.toLowerCase();
    } catch {
      return { valid: false, reason: "Malformed Origin header." };
    }
  } else if (refererHeader) {
    try {
      const u = new URL(refererHeader);
      if (u.origin === "null") {
        return { valid: false, reason: "Malformed Referer header (opaque origin)." };
      }
      requestOrigin = u.origin.toLowerCase();
    } catch {
      return { valid: false, reason: "Malformed Referer header." };
    }
  }

  if (!requestOrigin) {
    return {
      valid: false,
      reason: "Could not extract valid origin from request.",
    };
  }

  const trusted = getTrustedOrigins();
  if (trusted.has(requestOrigin)) {
    return { valid: true };
  }

  // Safe development check (e.g. dynamic port during local tests)
  if (isDevAllowedOrigin(requestOrigin)) {
    return { valid: true };
  }

  return {
    valid: false,
    reason: `Origin '${requestOrigin}' is not a trusted application origin.`,
  };
}
