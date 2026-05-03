/**
 * IIFE Module Entry Point — LiDAR Point Cloud Viewer
 *
 * Registers the module with the host via window.__NKZ__.register().
 * The host wraps all slot widgets with the moduleProvider (LidarProvider).
 */

import { lidarSlots } from './slots/index';

// Import App for side effects
import './App';

console.log('[nkz-module-lidar] 🟢 Bundle loaded v1.1.0');

const NKZ = (window as any).__NKZ__;
console.log('[nkz-module-lidar] __NKZ__:', typeof NKZ, 'register:', typeof NKZ?.register);

if (NKZ && typeof NKZ.register === 'function') {
  NKZ.register({
    id: 'lidar',
    viewerSlots: lidarSlots,
  });
  console.log('[nkz-module-lidar] ✅ Registered with slots:', Object.keys(lidarSlots));
} else {
  console.warn('[nkz-module-lidar] ❌ window.__NKZ__.register not available');
}
