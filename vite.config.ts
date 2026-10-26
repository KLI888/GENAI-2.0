import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const apiTarget = loadEnv(mode, '.', 'VITE_').VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000';

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': apiTarget,
        '/query': apiTarget,
        '/health': apiTarget,
        '/ingest': apiTarget,
        '/documents': apiTarget,
        '/stats': apiTarget,
        '/sources': apiTarget,
      },
    },
  };
});
