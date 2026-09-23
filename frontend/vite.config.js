import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// FinSight AI — Vite configuration.
//
// Infrastructure scope only. The dev-server proxy below forwards any
// request under /api to the local FastAPI backend, so the frontend can
// call relative paths (e.g. `/api/health`) in both development and
// production without hard-coding a backend origin in application code.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
