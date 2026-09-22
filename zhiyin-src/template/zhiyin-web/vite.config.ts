import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: "127.0.0.1",
    // 与 docker compose 里 web 服务对外暴露的 5173 对齐：本地开发与部署读同一个地址，
    // 不必先想"这次该开哪个端口"。
    port: 5173,
    proxy: {
      // 后端目标可配：默认 docker 外壳 8000；本地裸跑联调时
      // ZHIYIN_API_TARGET=http://127.0.0.1:8012 npm run dev
      '/api': { target: process.env.ZHIYIN_API_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: true },
      '/healthz': { target: process.env.ZHIYIN_API_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
