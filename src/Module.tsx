import { defineModule } from '@nekazari/module-kit';
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

// LidarProvider was previously a top-level slots.moduleProvider. SlotsSchema only
// accepts arrays per slot key, and each federated widget mounts into its own React
// tree. Strip moduleProvider and wrap every localComponent so widgets get their
// provider on mount.
const { moduleProvider: _moduleProvider, ...rawSlots } = lidarSlots as Record<string, unknown>;
const wrappedSlots = Object.fromEntries(
  Object.entries(rawSlots).map(([slot, entries]) => [
    slot,
    (entries as Array<Record<string, any>>).map((entry) => {
      const Inner = entry.localComponent as React.ComponentType<any> | undefined;
      if (!Inner) return entry;
      const Wrapped: React.FC<any> = (props) => (
        <LidarProvider>
          <Inner {...props} />
        </LidarProvider>
      );
      return { ...entry, localComponent: Wrapped };
    }),
  ]),
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
  slots: wrappedSlots as never,
});
