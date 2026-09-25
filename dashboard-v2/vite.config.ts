import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Served in production by the scanner's FastAPI process at :7777/v2/ (see
// scanner/api_v2.py mount_v2_static), so every asset URL is rooted at /v2/.
// In dev, /api is proxied to the live scanner; the alert WebSocket uses an
// absolute ws://host:7777 URL and needs no proxy. VITE_SCANNER_PORT points both at
// another scanner, e.g. the demo replay: VITE_SCANNER_PORT=7787 npm run dev
const scannerPort = process.env.VITE_SCANNER_PORT || '7777'

export default defineConfig({
  base: '/v2/',
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: { '/api': `http://localhost:${scannerPort}` },
  },
})
