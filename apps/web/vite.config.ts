import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['src/test/setup.ts'],
    exclude: ['**/node_modules/**', '**/e2e/**'],
    // Comfortably above the 5000ms Testing Library wait configured in `setup.ts`, so a
    // wait that genuinely exhausts itself reports *that* rather than tripping the test
    // timeout at the same instant and blaming the test. The default 5000ms was itself a
    // flake source: a slow render plus one retried wait already exceeded it.
    testTimeout: 15000,
  },
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      registerType: 'prompt',
      includeAssets: [
        'favicon.svg',
        'favicon.ico',
        'apple-touch-icon.png',
        'icon-192.png',
        'icon-384.png',
        'icon-512.png',
        'icon-1024.png',
        'icon-maskable-512.png',
        'coupon-icon.svg',
        'fonts/jetbrains-mono-600.woff2',
        'fonts/jetbrains-mono-700.woff2',
        'fonts/outfit-400.woff2',
        'fonts/outfit-600.woff2',
      ],
      manifest: {
        name: 'The Coupon',
        short_name: 'Coupon',
        description: 'A private weekly football accumulator game for friends. Points only.',
        theme_color: '#071A3D',
        background_color: '#071A3D',
        display: 'standalone',
        orientation: 'portrait',
        scope: '/',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-384.png', sizes: '384x384', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon-1024.png', sizes: '1024x1024', type: 'image/png' },
          { src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    rollupOptions: {
      output: {
        // Only carve out chunks Vite ALWAYS preloads on the entry — react +
        // router + query are eagerly used by App.tsx. framer-motion and
        // recharts are only used by lazy routes, so leaving them out lets
        // Rollup keep them inside those routes' chunks instead of preloading
        // them on the unauth /login entry.
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'query': ['@tanstack/react-query'],
        },
      },
    },
  },
  server: {
    port: process.env['PORT'] ? parseInt(process.env['PORT']) : 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
});
