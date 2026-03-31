import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const repositoryName = process.env.GITHUB_REPOSITORY?.split("/")[1];
const pagesBase =
  process.env.GITHUB_ACTIONS === "true" && repositoryName !== undefined
    ? `/${repositoryName}/`
    : "/";

export default defineConfig({
  base: pagesBase,
  plugins: [react()],
  server: {
    port: 5173,
  },
});
