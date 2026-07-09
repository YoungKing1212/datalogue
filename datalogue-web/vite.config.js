/* global process */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // 显式声明 streamdown 插件，避免 dev 冷启动 optimizeDeps 漏抓新加的插件
  optimizeDeps: {
    include: [
      '@streamdown/code',
      '@streamdown/math',
      '@streamdown/mermaid',
      '@streamdown/cjk',
    ],
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setup.js',
  },
  server: {
    hmr: {
      // 限制 HMR 重连次数，防止无限轮询导致 CPU 100%
      timeout: 3000,
    },
    proxy: {
      '/api/': {
        target: apiProxyTarget,
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
