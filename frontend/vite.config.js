import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Installable app (Add to Home Screen) + offline-friendly menu
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'icons/apple-touch-icon.png'],
      manifest: {
        name: 'LAGOM',
        short_name: 'LAGOM',
        description: 'LAGOM — Food · Drinks · Moments. Order and pay from your table.',
        lang: 'en',
        theme_color: '#263D31',
        background_color: '#F3EBDD',
        display: 'standalone',
        orientation: 'any',
        start_url: '/',
        scope: '/',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        // Keep the first download small for customers on mobile data:
        globIgnores: [
          'splash/**', // iPhone splash images are only needed when installing
          '**/*-{cyrillic,cyrillic-ext,greek,greek-ext,vietnamese}-*.woff2', // alphabets LAGOM does not use
          // Staff screens (they need internet anyway) are not stored on customers' phones
          '**/{AdminApp,Overview,Orders,Payments,MenuAdmin,Tables,SettingsPage,Inventory,Finance,StaffPage,AuditLog,MyAccount,PosApp,KdsApp,LoginPage,Receipt}-*.js',
        ],
        // A table link opened offline still shows the app (and the cached menu)
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/uploads\//],
        runtimeCaching: [
          {
            // Menu and public settings: show the last copy at once, refresh in the background
            urlPattern: ({ url }) => url.pathname === '/api/public/menu' || url.pathname === '/api/settings/public',
            handler: 'StaleWhileRevalidate',
            options: { cacheName: 'lagom-menu', expiration: { maxAgeSeconds: 7 * 24 * 3600 } },
          },
          {
            // Food photos
            urlPattern: ({ request }) => request.destination === 'image',
            handler: 'CacheFirst',
            options: {
              cacheName: 'lagom-images',
              expiration: { maxEntries: 200, maxAgeSeconds: 30 * 24 * 3600 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          // Everything else under /api (orders, payments, staff) is never cached: always live
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    port: 5173,
    // During development, API calls go to the local FastAPI server
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: true },
      '/uploads': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  test: {
    environment: 'node',
  },
})
