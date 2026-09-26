/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// No dev, o Vite repassa /panel e /api à API local; em produção o Caddy serve o build
// e encaminha só esses dois prefixos.
const API_TARGET = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/panel": API_TARGET,
      "/api": API_TARGET,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
