import type { NextConfig } from "next";

/**
 * The dashboard talks to the FastAPI backend through same-origin `/v1/*` requests, so the
 * HttpOnly session cookie and signed file URLs work without CORS. In development (and in the
 * single-container setup) Next.js forwards them with a rewrite; in production a reverse proxy
 * (see deploy/Caddyfile) routes `/v1/*` to the API directly, which also streams large uploads.
 */
const API_URL = process.env.BDNA_API_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/v1/:path*", destination: `${API_URL}/v1/:path*` },
      { source: "/health", destination: `${API_URL}/health` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
