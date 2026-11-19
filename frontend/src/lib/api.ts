/**
 * Typed client for same-origin BFF API requests.
 * All requests route to Next.js BFF proxy (/api/v1/*) — credentials (HttpOnly cookie)
 * are managed automatically by the browser. Session tokens are never stored in JavaScript memory
 * or browser storage; one-time API keys and webhook signing secrets exist strictly in transient
 * React state during deliberate user reveal.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, params, headers: customHeaders, ...fetchOptions } = options;

  let url = path.startsWith("/") ? path : `/${path}`;
  if (!url.startsWith("/api/")) {
    url = `/api/v1${url}`;
  }

  if (params) {
    const searchParams = new URLSearchParams();
    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== null) {
        searchParams.append(key, String(val));
      }
    }
    const queryStr = searchParams.toString();
    if (queryStr) {
      url += (url.includes("?") ? "&" : "?") + queryStr;
    }
  }

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(customHeaders as Record<string, string>),
  };

  let serializedBody: BodyInit | undefined = undefined;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    serializedBody = JSON.stringify(body);
  }

  const res = await fetch(url, {
    ...fetchOptions,
    headers,
    body: serializedBody,
    credentials: "same-origin",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    const message =
      (typeof errorData?.detail === "string" ? errorData.detail : null) ??
      errorData?.message ??
      `Request failed with status ${res.status}`;

    // If 401 Unauthorized occurs on client side, notify session listeners
    if (res.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("agent-session-expired"));
    }

    throw new ApiError(res.status, message, errorData?.detail ?? errorData);
  }

  if (res.status === 204) {
    return null as T;
  }

  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "GET" }),

  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "POST", body }),

  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PUT", body }),

  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PATCH", body }),

  del: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "DELETE" }),
};
