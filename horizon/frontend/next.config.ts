import type { NextConfig } from "next";

// L'API FastAPI est servie en même origine via /api/* (cookies SameSite=Strict, pas de CORS).
// BACKEND_URL est lu au moment du build/démarrage (voir README).
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${backend}/v1/:path*` },
      { source: "/api/health", destination: `${backend}/health` },
      { source: "/api/ready", destination: `${backend}/ready` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
