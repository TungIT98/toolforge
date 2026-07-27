import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  server: {
    port: 3000,
    proxy: {
      // Proxy /api/* to local Worker (when wrangler dev runs on 8787)
      "/api": {
        target: "http://localhost:8787",
        changeOrigin: true,
      },
    },
  },
});
