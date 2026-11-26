import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Proxy dev : l'API FastAPI tourne sur http://localhost:8000.
// En production, le build (dist/) est servi directement par l'API (SPA fallback).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
  },
});
