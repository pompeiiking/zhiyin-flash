import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
const env = loadEnv(mode, '.', 'ZHIYIN_')
return {
  plugins: [vue()],
  resolve: {
    alias: {
      // 用 root 相对路径，省掉 node:url 与 @types/node 依赖
      '@': '/src',
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5275,
    // 与开发说明保持一致；端口被占用时直接报错，不自动漂移。
    strictPort: true,
    proxy: { '/api': { target: env.ZHIYIN_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  preview: {
    host: '127.0.0.1',
    port: 5275,
  },
}
})
