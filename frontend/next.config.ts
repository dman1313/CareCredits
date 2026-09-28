import type { NextConfig } from 'next';

const distDir = process.env.NEXT_DIST_DIR?.trim();
const nextConfig: NextConfig = {
  output: 'standalone',
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
  ...(distDir ? { distDir } : {}),
};
export default nextConfig;
