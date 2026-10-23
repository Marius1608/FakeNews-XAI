import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    strictPort: true, // fail instead of moving to :3001 — backend CORS allows only :3000
  },
  preview: {
    port: 3000,
  },
  build: {
    outDir: "build", // same folder as CRA → Dockerfile and backend paths stay the same
    emptyOutDir: true,
  },
});
