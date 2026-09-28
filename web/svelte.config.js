import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter(),
    paths: { base: process.env.BASE_PATH ?? "" },
    alias: {
      $data: "../data/site",
      $docs: "../docs",
    },
  },
};

export default config;
