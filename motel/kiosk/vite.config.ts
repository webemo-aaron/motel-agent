import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.MOTEL_KIOSK_PORT ?? 5182),
    strictPort: true,
    proxy: {
      "/api/motel": `http://localhost:${process.env.MOTEL_API_PORT ?? 8653}`,
      "/api/voice": `http://localhost:${process.env.MOTEL_API_PORT ?? 8653}`,
      "/api/hermes": {
        target: `http://localhost:${process.env.MOTEL_HERMES_PORT ?? 8652}`,
        rewrite: (path) => path.replace(/^\/api\/hermes/, ""),
        changeOrigin: true,
        headers: {
          "Authorization": "Bearer test-key-for-local-development"
        }
      },
    },
  },
});
