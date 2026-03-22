import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

function proxyErrorHandler(proxy) {
  proxy.on('error', (err, req, res) => {
    console.warn(`[Vite Proxy] Backend not reachable (${err.code || err.message})`)
    if (res && !res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: 'Backend server is not reachable. Please start the server.' }))
    }
  })
}

export default defineConfig({
  plugins: [vue()],
  base: '/',
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') }
  },
  build: {
    outDir: path.resolve(__dirname, '../qengine/static'),
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    proxy: {
      '/ws': {
        target: 'ws://localhost:9000',
        ws: true,
        configure: (proxy) => {
          proxy.on('error', (err) => {
            console.warn('[Vite Proxy] WS backend not reachable:', err.code || err.message)
          })
        }
      },
      '/auth': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/broker': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/market-data': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/settings': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/llm': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/backtest': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/config': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/exchange': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/candles': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/strategy': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/live': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/optimization': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/monte-carlo': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/playground': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/system': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/download': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/closed-trades': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/orders': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/notification': { target: 'http://localhost:9000', configure: proxyErrorHandler },
      '/issues': { target: 'http://localhost:9000', configure: proxyErrorHandler },
    }
  }
})
