import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// GitHub Pages serves the site from /<repo>/ (or / on a custom domain);
// the deploy workflow passes the right prefix via VITE_BASE_PATH.
export default defineConfig({
  base: process.env.VITE_BASE_PATH || '/',
  plugins: [
    tailwindcss(),
    react(),
  ],
})
