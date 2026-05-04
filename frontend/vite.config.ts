/// <reference types="vitest" />
import { defineConfig, type UserConfig } from "vite";
import react from "@vitejs/plugin-react";

const config: UserConfig & { test?: Record<string, unknown> } = {
  plugins: [react()],
  resolve: {
    // TS/TSX before JS so a stray compiled .js next to a .tsx source can't
    // silently shadow the real source during dev or tests.
    extensions: [".mjs", ".ts", ".tsx", ".js", ".jsx", ".json"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 1000,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    css: false,
  },
};

export default defineConfig(config);
