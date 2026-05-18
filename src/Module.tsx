import { defineModule, withModuleProvider } from '@nekazari/module-kit';
import React, { lazy, Suspense } from 'react';
import './i18n';
import { lidarSlots } from './slots';
import { LidarProvider } from './services/lidarContext';
import pkg from '../package.json';

const LazyApp = lazy(() => import('./App'));

const MainWrapper: React.FC = () => (
  <LidarProvider>
    <Suspense fallback={<div className="p-8 text-center">Loading LiDAR…</div>}>
      <LazyApp />
    </Suspense>
  </LidarProvider>
);

export default defineModule({
  id: 'lidar',
  displayName: 'LiDAR Point Cloud',
  version: pkg.version,
  hostApiVersion: '^2.0.0',
  description: 'LIDAR point cloud viewer (LAZ from IDENA, Cesium 3D Tiles) — Nekazari Platform Module',
  accent: { base: '#0EA5E9', soft: '#E0F2FE', strong: '#0369A1' },
  icon: 'mountain-snow',
  main: MainWrapper,
  api: { basePath: '/api/lidar' },
  slots: withModuleProvider(lidarSlots) as never,
});
