import type { NextConfig } from "next";

// Static export: o FastAPI serve o build (pasta out/) na mesma origem da API,
// mantendo o cookie de sessão HttpOnly sem CORS (ver Arquitetura, seção 1).
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
