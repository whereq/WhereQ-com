import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  build: {
    // Match tsconfig.app.json's `lib: ES2022` — the two must agree, otherwise
    // the compiler allows an API the emitted bundle may not run on.
    target: 'es2022',
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      'react': path.resolve(__dirname, '../node_modules/react'),
      'react-dom': path.resolve(__dirname, '../node_modules/react-dom'),
    },
    dedupe: ['react', 'react-dom'],
  },
  server: {
    port: 3743,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // The friend-location socket uses the page origin (same-origin in
        // production, where nginx proxies /api to the API container), so the
        // dev proxy has to carry WebSocket upgrades too.
        ws: true,
      },
    },
  },
})
