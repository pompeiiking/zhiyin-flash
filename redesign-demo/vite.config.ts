import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      // 用 root 相对路径，省掉 node:url 与 @types/node 依赖
      '@': '/src',
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5273,
    /*
     * strictPort: 端口被占用时**直接失败**，不要悄悄换成 5274。
     * 评审手上拿的链接是写死的 5273 —— 服务换到别的端口，链接就打不开了，
     * 而现象是"有时候打得开有时候打不开"，极难查。宁可起不来（报错看得见）。
     */
    strictPort: true,
  },
  preview: {
    host: '127.0.0.1',
    port: 5273,
  },
})
