import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // All API calls are proxied through Next.js — no secrets exposed to browser
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL ?? "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
