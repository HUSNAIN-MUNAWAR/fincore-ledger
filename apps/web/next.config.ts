import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  experimental: {
    webpackBuildWorker: false,
  },
};

export default nextConfig;
