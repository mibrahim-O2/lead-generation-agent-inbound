import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// VITE_BASE is the path the site is served from. GitHub Pages serves a project
// site from "/<repo-name>/", so the Pages workflow sets it. Locally it is "/".
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "VITE_");
  return {
    base: env.VITE_BASE || "/",
    plugins: [react()],
  };
});
