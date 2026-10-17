import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api requests are proxied to FastAPI so the browser sees a single origin in dev
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": process.env.API_URL || "http://localhost:8000",
      "/uploads": process.env.API_URL || "http://localhost:8000",
    },
  },
});
