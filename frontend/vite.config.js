import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // During development, API calls go to the local FastAPI server
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: true },
    },
  },
  test: {
    environment: 'node',
  },
})
