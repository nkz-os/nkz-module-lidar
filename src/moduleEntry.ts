/**
 * IIFE Module Entry Point — LiDAR Point Cloud Viewer
 *
 * Registers the module with the host via window.__NKZ__.register().
 * The host wraps all slot widgets with the moduleProvider (LidarProvider).
 */

import { lidarSlots } from './slots/index';

// Import CSS so it's inlined in the IIFE bundle
import './index.css';

const NKZ = (window as any).__NKZ__;
if (NKZ && typeof NKZ.register === 'function') {
  NKZ.register({
    id: 'lidar',
    viewerSlots: lidarSlots,
  });
} else {
  console.warn('[nkz-module-lidar] window.__NKZ__.register not available');
}
