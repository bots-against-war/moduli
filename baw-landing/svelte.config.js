/*
  This is a SvelteKit config for rendering landing to static page!
  SvelteKit insists on having it in project root. The main web app
  and its Svete (not SvelteKit) configuration  live in frontend/
*/

import adapter from "@sveltejs/adapter-static";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

let base = process.env.BASE_PATH;
const paths = base
  ? {
      base: base,
      relative: false,
    }
  : {};

console.log(`Building landing with paths option: ${JSON.stringify(paths)}`);

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: "dist",
      assets: "dist",
      fallback: undefined,
      precompress: false,
      strict: true,
    }),
    paths,
    appDir: "assets",
    files: {
      assets: "static",
      routes: "src/routes",
      appTemplate: "src/app.html",
    },
    outDir: "build-kit",
    prerender: {
      handleHttpError: "warn",
    },
  },
};

export default config;
