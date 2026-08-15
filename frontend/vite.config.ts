import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 转发到本机 FastAPI（ave/server.py 跑在 8756）
    proxy: {
      '/api': 'http://127.0.0.1:8756',
    },
  },
})
