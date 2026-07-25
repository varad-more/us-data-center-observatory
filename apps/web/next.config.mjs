/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle so the production Docker image does not
  // need node_modules copied into it.
  output: "standalone",
  eslint: {
    // Linting runs as its own CI step; keeping it out of the build makes build
    // failures unambiguous.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
