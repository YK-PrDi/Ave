import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    // 显式绑 IPv4。默认的 localhost 在本机会解析到 IPv6 [::1]，
    // 导致启动.bat 的就绪检查（连 127.0.0.1）一直连不上。
    host: '127.0.0.1',
    port: 5173,
    // 转发到本机 FastAPI（ave/server.py 跑在 8756）
    proxy: {
      '/api': 'http://127.0.0.1:8756',
    },
  },
})
