import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // All API requests are securely mediated by Next.js BFF Route Handlers
  // (/api/auth/* and /api/v1/*) with server-side HttpOnly cookie session injection,
  // origin validation, and strict cache-control.
  // Direct client rewrites are removed to enforce the security boundary.
  reactStrictMode: true,
};

export default nextConfig;
