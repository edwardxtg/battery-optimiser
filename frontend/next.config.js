/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static HTML export → deployable as plain files on any static host (your website,
  // Vercel, Cloudflare Pages, GitHub Pages). No server runtime, zero running cost.
  output: "export",
  images: { unoptimized: true },
};

module.exports = nextConfig;
