/** @type {import('next').NextConfig} */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "/project-helios";

// "export" produces a fully static site for GitHub Pages (no Node server needed).
// "standalone" produces a self-contained Node server for Docker deployment.
// Set NEXT_OUTPUT_MODE=standalone when building the Docker image.
const outputMode = process.env.NEXT_OUTPUT_MODE || "export";

const nextConfig = {
  reactStrictMode: true,
  output: outputMode,
  basePath,
  images: {
    unoptimized: true,
  },
  eslint: {
    // Linting runs as its own CI step; keeping it out of the build makes build
    // failures unambiguous.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
