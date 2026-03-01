import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// IIFE build for Nekazari runtime module injection
export default defineConfig({
  plugins: [
    react({ jsxRuntime: 'classic' }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5004,
    cors: true,
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        secure: true,
      },
    },
  },
  build: {
    target: 'es2020',
    minify: true,
    cssCodeSplit: false,
    lib: {
      entry: path.resolve(__dirname, 'src/moduleEntry.ts'),
      name: 'NkzModuleLidar',
      formats: ['iife'],
      fileName: () => 'nkz-module.js',
    },
    rollupOptions: {
      external: [
        'react',
        'react-dom',
        'react-dom/client',
        'react-router-dom',
        '@nekazari/sdk',
        '@nekazari/ui-kit',
      ],
      output: {
        globals: {
          'react': 'React',
          'react-dom': 'ReactDOM',
          'react-dom/client': 'ReactDOM',
          'react-router-dom': 'ReactRouterDOM',
          '@nekazari/sdk': '__NKZ_SDK__',
          '@nekazari/ui-kit': '__NKZ_UI__',
        },
        inlineDynamicImports: true,
      },
    },
  },
});
