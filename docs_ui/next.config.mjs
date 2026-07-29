/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output produces a minimal production server bundle
  // (~70% smaller Docker images). See Dockerfile `runner` stage.
  output: "standalone",
  trailingSlash: false,
  reactStrictMode: true,
  poweredByHeader: false,
  compress: true,

  // Image optimization.
  //
  // SECURITY: `dangerouslyAllowSVG` + wildcard `remotePatterns` is an XSS
  // footgun. We mitigate by forcing a strict CSP on image responses.
  // Tighten `remotePatterns` to your actual image hosts in production.
  images: {
    formats: ["image/avif", "image/webp"],
    minimumCacheTTL: 86400,
    dangerouslyAllowSVG: true,
    contentDispositionType: "inline",
    contentSecurityPolicy:
      "default-src 'self'; script-src 'none'; style-src 'unsafe-inline'; sandbox;",
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },

  // Turbopack optimizations (top-level)
  turbopack: {
    resolveExtensions: [".tsx", ".ts", ".jsx", ".js", ".mjs", ".json"],
  },

  // Experimental features for performance
  experimental: {
    optimizePackageImports: ["@heroui/react", "@heroui/styles"],
    optimizeCss: true,
    useTypeScriptCli: true,
  },

  // Headers for caching and security
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "X-DNS-Prefetch-Control",
            value: "on",
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "X-Frame-Options",
            value: "SAMEORIGIN",
          },
          // X-XSS-Protection intentionally omitted: deprecated/harmful
          // on modern browsers. Use a Content-Security-Policy instead.
          {
            key: "Referrer-Policy",
            value: "origin-when-cross-origin",
          },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
      {
        // Cache static assets - 1 week (Next.js cache busting via content hashing)
        source: "/images/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=604800",
          },
        ],
      },
      {
        // Cache fonts - 1 week
        source: "/fonts/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=604800",
          },
        ],
      },
      {
        // Cache Next.js static chunks (JS/CSS) - 1 week
        // Next.js uses content hashing in filenames, so new builds get new URLs
        source: "/_next/static/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=604800",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
