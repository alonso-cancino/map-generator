import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  build: {
    emptyOutDir: false,
    lib: {
      entry: resolve(__dirname, "src/index.ts"),
      fileName: "index",
      formats: ["es"],
    },
    outDir: "dist-lib",
    rollupOptions: {
      external: ["react", "react-dom"],
    },
  },
  plugins: [react()],
  publicDir: false,
});
