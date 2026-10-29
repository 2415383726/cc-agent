import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue(), {
    name: 'visualize-sandbox-policy',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        if (request.url?.split('?')[0].endsWith('/visualize/sandbox.html')) {
          response.setHeader('Connection-Allowlist', '()')
          response.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), display-capture=(), usb=()')
          response.setHeader('Cache-Control', 'no-store')
        }
        next()
      })
    },
  }],
  base: './',
  build: {
    target: 'es2022',
    assetsInlineLimit: 0,
    sourcemap: false,
  },
  test: {
    environment: 'happy-dom',
    include: ['tests/**/*.test.ts'],
  },
})
