import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Browser QA has neither environment-file loading nor a backend API proxy.
// Tests must install synthetic fetch fixtures before navigating to this server.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: false,
  server: { host: '127.0.0.1', port: 5187, strictPort: true },
})
