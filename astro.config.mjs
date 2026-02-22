// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from "@tailwindcss/vite";

import mdx from "@astrojs/mdx";

import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://www.jake.ac",
  vite: {
    plugins: [tailwindcss()],
  },
  integrations: [mdx(), sitemap()],
});