import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: Number(env.VITE_DEV_PORT ?? 13000),
      host: env.VITE_DEV_HOST ?? "0.0.0.0",
      proxy: {
        // dev 模式下 /api/ 代理到 forge-server。
        // 必须用 `^/api/` 正则锚定前缀，不然 `/api-keys` 会被吞掉转发给后端。
        "^/api/.*": {
          target: env.VITE_DEV_API_TARGET ?? "http://localhost:13001",
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: mode !== "production",
    },
  };
});
