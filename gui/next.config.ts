import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    // Client-side /api/* calls must reach the SAME worker the server
    // components use (NEXT_PUBLIC_WORKER_URL) — not a hardcoded localhost
    // port. The VPS launcher points at the remote worker; without this,
    // every /api/* call 500s while direct fetches keep working.
    const workerURL = (
      process.env.NEXT_PUBLIC_WORKER_URL || "http://127.0.0.1:8000"
    ).trim().replace(/\/+$/, "");
    return [
      {
        source: "/api/:path*",
        destination: `${workerURL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
