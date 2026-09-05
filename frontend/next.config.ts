import type { NextConfig } from "next";
import path from "path";

const isStaticExport = process.env.STATIC_EXPORT?.trim() === "true" || process.env.OUTPUT_EXPORT === "true";

const nextConfig: NextConfig = {
  ...(isStaticExport ? { output: "export" } : {}),
  typescript: {
    ignoreBuildErrors: true,
  },
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      extend: path.resolve(process.cwd(), "node_modules/extend/index.js"),
    };
    return config;
  },
  ...(isStaticExport
    ? {}
    : {
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: "http://127.0.0.1:8000/api/:path*",
            },
          ];
        },
      }),
};

export default nextConfig;
