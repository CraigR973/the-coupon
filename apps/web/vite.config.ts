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
    // Pin the runner's zone away from UTC (Batch 43). Every date this app renders is
    // converted into the *member's* zone, so a test whose process runs in UTC cannot
    // tell a correctly-parsed instant from one parsed as local time — the numbers are
    // identical. CI runs in UTC and this Mac runs in Europe/London, so the same suite
    // was strict in one place and blind in the other. `America/New_York` is never equal
    // to UTC or to London under either DST rule, so a mis-parse always shows.
    env: { TZ: 'America/New_York' },
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
        'fonts/outfit-400.woff2',
        'fonts/outfit-600.woff2',
      ],
      manifest: {
        name: 'The Coupon',
        short_name: 'Coupon',
        description: 'A private weekly football accumulator game for friends. Points only.',
        id: '/',
        theme_color: '#0B0E13',
        background_color: '#0B0E13',
        display: 'standalone',
        orientation: 'portrait',
        scope: '/',
        start_url: '/',
        screenshots: [
          { src: '/screenshots/login-phone.png', sizes: '390x844', type: 'image/png', form_factor: 'narrow', label: 'The Coupon sign-in on a phone' },
          { src: '/screenshots/login-desktop.png', sizes: '1280x800', type: 'image/png', form_factor: 'wide', label: 'The Coupon sign-in on a desktop' },
        ],
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
    // Vite 5's default. Vite 8 would raise it to Safari 16.4 (Batch 202 changed the
    // toolchain, not who can run the app).
    target: ['es2020', 'edge88', 'firefox78', 'chrome87', 'safari14'],
    rolldownOptions: {
      output: {
        // Only carve out chunks Vite ALWAYS preloads on the entry — react +
        // router + query are eagerly used by App.tsx. recharts is only used by
        // lazy routes, so leaving it out keeps it inside those routes' chunks
        // instead of preloading it on the unauth /login entry. Rolldown takes
        // these as groups that, like Rollup's object form, bring each package's
        // own dependencies along.
        codeSplitting: {
          groups: [
            {
              name: 'react-vendor',
              test: /[\\/]node_modules[\\/](react|react-dom|react-router-dom)[\\/]/,
              priority: 2,
            },
            {
              name: 'query',
              test: /[\\/]node_modules[\\/]@tanstack[\\/]react-query[\\/]/,
              priority: 1,
            },
          ],
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
