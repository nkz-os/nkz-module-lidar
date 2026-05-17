import { defineConfig } from 'vite';
import { nkzModulePreset } from '@nekazari/module-builder';
import path from 'path';

export default defineConfig(
  nkzModulePreset({
    viteConfig: {
      resolve: {
        alias: { '@': path.resolve(__dirname, './src') },
      },
      server: {
        host: '0.0.0.0',
        port: 5004,
        cors: true,
        proxy: {
          '/api': {
            target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
            changeOrigin: true,
            secure: true,
          },
        },
      },
    },
  }),
);
