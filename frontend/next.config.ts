import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "/v2",
  // Allow images from any domain (job logos, etc.)
  images: { unoptimized: true },
};

export default nextConfig;
