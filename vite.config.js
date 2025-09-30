import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// Use BASE_PATH env variable or default to '/'
const basePath = process.env.BASE_PATH || '/'

export default defineConfig({
  plugins: [svelte()],
  base: basePath
})