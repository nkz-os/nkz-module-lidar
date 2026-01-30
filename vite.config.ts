import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import federation from '@originjs/vite-plugin-federation';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    federation({
      name: 'lidar_module',
      filename: 'remoteEntry.js',
      exposes: {
        // Main app component
        './App': './src/App.tsx',
        // viewerSlots for unified viewer integration - MUST be named './viewerSlots' for host compatibility
        './viewerSlots': './src/slots/index.tsx',
        // Individual components (for direct import)
        './LidarLayerControl': './src/components/slots/LidarLayerControl.tsx',
        './LidarLayer': './src/components/slots/LidarLayer.tsx',
        './LidarConfig': './src/components/slots/LidarConfig.tsx',
        // Context provider
        './LidarProvider': './src/services/lidarContext.tsx',
      },
      shared: {
        'react': {
          singleton: true,
          requiredVersion: '^18.3.1',
          import: false,
          shareScope: 'default',
        },
        'react-dom': {
          singleton: true,
          requiredVersion: '^18.3.1',
          import: false,
          shareScope: 'default',
        },
        'react-router-dom': {
          singleton: true,
          requiredVersion: '^6.26.0',
          import: false,
          shareScope: 'default',
        },
        '@nekazari/ui-kit': {
          singleton: true,
          requiredVersion: '^1.0.0',
          import: false,
          shareScope: 'default',
        },
        // Note: @nekazari/sdk is implemented locally in src/sdk/
        // It connects to window.__nekazariViewerContext provided by the host
      },
    }),
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
    // Proxy API calls to avoid CORS issues in development
    proxy: {
      '/api': {
        target: 'https://nkz.artotxiki.com',
        changeOrigin: true,
        secure: true,
      },
    },
  },
  build: {
    target: 'esnext',
    minify: false,  // Keep false for Module Federation compatibility
    cssCodeSplit: false,
    rollupOptions: {
      external: ['react', 'react-dom', 'react-router-dom'],
      output: {
        globals: {
          'react': 'React',
          'react-dom': 'ReactDOM',
          'react-router-dom': 'ReactRouterDOM',
        },
      },
    },
  },
});
