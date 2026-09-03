import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    // Docker / WSL / 远程开发时需要让宿主机 / 其他机器访问 dev server
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: `http://${process.env.VITE_BACKEND_HOST || 'localhost'}:8000`,
        changeOrigin: true,
      },
    },
  },
  build: {
    // 提升对旧 Chrome / Edge 的兼容（默认 esnext = ES2022，部分老用户浏览器未跟进）
    target: 'es2020',
    // 提高告警阈值（markmap 已改为按需异步加载，不再阻塞首屏）
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // 第三方依赖细分包：提升浏览器缓存命中率，
        // markmap + d3 单独成块且因动态 import 仅在使用思维导图时加载。
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('markmap') || id.includes('/d3') || id.includes('d3-') || id.includes('katex')) return 'markmap'
            if (id.includes('axios')) return 'axios'
            if (id.includes('marked')) return 'marked'
            if (id.includes('/vue/') || id.includes('@vue') || id.includes('vue-router')) return 'vue'
            return 'vendor'
          }
        },
      },
    },
  },
})
