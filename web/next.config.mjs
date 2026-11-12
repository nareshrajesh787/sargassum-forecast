/** Static export: the whole site is plain files on Vercel; data comes from /api/v1/*.json committed by the daily job. */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};
export default nextConfig;
