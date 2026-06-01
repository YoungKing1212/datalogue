import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    hmr: {
      // 限制 HMR 重连次数，防止无限轮询导致 CPU 100%
      timeout: 3000,
    },
    proxy: {
      '/api/': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            delete proxyRes.headers['content-length'];
          });
        },
      },
    },
  },
})
