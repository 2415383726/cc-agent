import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import manifest from './src/visualize/manifest.json'
import { sandboxPolicy } from './src/visualize/kit'

export default defineConfig({
  plugins: [vue(), {
    name: 'visualize-sandbox-policy',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        if (request.url?.split('?')[0].endsWith('/visualize/sandbox.html')) {
          response.setHeader('Connection-Allowlist', '()')
          response.setHeader('Content-Security-Policy', sandboxPolicy)
          response.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), display-capture=(), usb=()')
          response.setHeader('Cache-Control', 'no-store')
        }
        next()
      })
    },
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'visualize/manifest.json', source: JSON.stringify(manifest, null, 2) })
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
