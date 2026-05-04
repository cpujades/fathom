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
  }
};

export default nextConfig;
