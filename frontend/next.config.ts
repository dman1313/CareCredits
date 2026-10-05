import path from 'path';
import type { NextConfig } from 'next';

function distDirInsideApp(raw?: string) {
  const value = (raw || '').trim();
  if (!value) return undefined;
  const root = process.cwd();
  const resolved = path.resolve(root, value);
  if (resolved === root || resolved.startsWith(root + path.sep)) {
    return path.relative(root, resolved) || '.next';
  }
  return path.join('.data', path.basename(resolved) || 'next-dev');
}

const distDir = distDirInsideApp(process.env.NEXT_DIST_DIR);
const nextConfig: NextConfig = {
  output: 'standalone',
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
  ...(distDir ? { distDir } : {}),
};
export default nextConfig;
