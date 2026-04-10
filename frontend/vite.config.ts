import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

function parseAllowedHosts(rawValue?: string) {
  return String(rawValue || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const allowedHosts = Array.from(
    new Set([
      'localhost',
      '127.0.0.1',
      ...parseAllowedHosts(env.VITE_ALLOWED_HOSTS),
      ...parseAllowedHosts(env.__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS),
    ]),
  )

  return {
    plugins: [vue()],
    server: {
      allowedHosts,
    },
  }
})
