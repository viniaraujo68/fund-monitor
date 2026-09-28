import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  build: {
    cssTarget: ["chrome123", "edge123", "firefox120", "safari17.5"],
  },
  server: {
    fs: {
      allow: ["../data/site"],
    },
  },
});
