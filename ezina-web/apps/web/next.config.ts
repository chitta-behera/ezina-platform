import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Fully static site for Cloudflare Pages: `next build` writes plain HTML/CSS/JS to ./out
  output: "export",
  // No image optimisation server in a static export; images in /public are pre-optimised.
  images: { unoptimized: true },
  // @ezina/ui ships TypeScript source.
  transpilePackages: ["@ezina/ui"],
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;
