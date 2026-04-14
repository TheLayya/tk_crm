import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig(({ mode }) => {
  // 用 __dirname 确保始终读到 frontend/.env，不受启动目录影响
  const env = loadEnv(mode, path.resolve(__dirname), '')
  const backendUrl = env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

  console.log(`[vite] proxy /api -> ${backendUrl}`)

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src')
      }
    },
    server: {
      proxy: {
        '/api': {
          target: backendUrl,
          changeOrigin: true
        }
      }
    }
  }
})
