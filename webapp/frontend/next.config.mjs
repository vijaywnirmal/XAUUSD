/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  experimental: {
    // Next's dev-server rewrite proxy defaults to a 30s upstream timeout
    // (next/dist/server/lib/router-utils/proxy-request.js) — too short for
    // the Strategy Builder's Ollama-backed NL parse, which can take 30-120s+
    // on CPU-only inference. 10 minutes covers that with margin.
    proxyTimeout: 600_000,
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:8000/:path*',
      },
    ]
  },
}

export default nextConfig
