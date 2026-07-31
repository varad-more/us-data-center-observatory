/** @type {import('next').NextConfig} */
// Empty by default because the site is served from the root of its own host,
// us-data-center-observatory.varadmore.me. A custom domain has no repository
// segment in the path, so the /project-helios prefix this used to carry would
// send every asset to a 404. Set NEXT_PUBLIC_BASE_PATH to deploy under a
// subdirectory instead - a fork on <user>.github.io/<repo> needs "/<repo>".
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

// "export" produces a fully static site for GitHub Pages (no Node server needed).
// "standalone" produces a self-contained Node server for Docker deployment.
// Set NEXT_OUTPUT_MODE=standalone when building the Docker image.
const outputMode = process.env.NEXT_OUTPUT_MODE || "export";

const nextConfig = {
  reactStrictMode: true,
  output: outputMode,
  // Omitted entirely when empty: Next treats basePath: "" as a configured value
  // and warns, where an absent key is the documented way to say "serve at root".
  ...(basePath ? { basePath } : {}),
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
