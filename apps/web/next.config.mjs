import { buildSecurityHeaders } from "./app/lib/securityHeaders.mjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@fathom/api-client"],
  allowedDevOrigins: ["127.0.0.1", "localhost", "carloss-macbook-pro.tailcd69ae.ts.net"],
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "i.ytimg.com"
      }
    ]
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: buildSecurityHeaders(process.env)
      }
    ];
  }
};

export default nextConfig;
