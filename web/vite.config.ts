import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const isDev = mode === 'development' || process.env.CLOUDLENS_ENV === 'development';

  return {
    plugins: [
      {
        name: 'prune-dev-showcase',
        resolveId(id) {
          if (!isDev && id.includes('DesignSystemShowcase')) {
            return '\0virtual:empty-dev-showcase';
          }
          return null;
        },
        load(id) {
          if (id === '\0virtual:empty-dev-showcase') {
            return 'export const DesignSystemShowcase = () => null; export default DesignSystemShowcase;';
          }
          return null;
        },
      },
      react(),
    ],
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules')) {
              if (id.includes('lucide-react')) return 'vendor-icons';
              if (id.includes('react-router')) return 'vendor-router';
              if (id.includes('react') || id.includes('scheduler')) return 'vendor-react';
              return 'vendor-libs';
            }
            if (!isDev && (id.includes('DesignSystemShowcase') || id.includes('empty-dev-showcase'))) {
              return undefined;
            }
            if (id.includes('/pages/')) {
              const match = id.match(/\/pages\/([^/]+)\.(?:tsx|ts)/);
              if (match && match[1]) {
                if (!isDev && match[1] === 'DesignSystemShowcase') return undefined;
                return `route-${match[1]}`;
              }
            }
          },
        },
      },
    },
    server: {
      port: 3000,
      host: true,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    preview: {
      port: 4173,
      host: true,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  };
});
