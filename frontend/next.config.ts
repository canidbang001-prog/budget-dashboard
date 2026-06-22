import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'export',
  trailingSlash: true,
  // API는 FastAPI가 같은 포트에서 직접 서빙하므로 rewrite 불필요
};

export default nextConfig;
