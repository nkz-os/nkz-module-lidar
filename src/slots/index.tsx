/**
 * Slot Registration for LIDAR Module
 *
 * Layout:
 *   layer-toggle  → LidarLayerToggle (lightweight status + color mode pills)
 *   context-panel → LidarLayerControl (full controls: coverage, download, upload, layers)
 *   context-panel → LidarConfig (tree info, results summary)
 *   map-layer     → LidarLayer (Cesium 3D Tiles renderer)
 */

import React from 'react';
import LidarLayerToggle from '../components/slots/LidarLayerToggle';
import LidarLayerControl from '../components/slots/LidarLayerControl';
import { LidarLayer } from '../components/slots/LidarLayer';
import { LidarConfig } from '../components/slots/LidarConfig';
import { LidarProvider } from '../services/lidarContext';

// Module identifier - used for all slot widgets
const MODULE_ID = 'lidar';

export interface SlotWidgetDefinition {
  id: string;
  /**
   * Module ID that owns this widget. REQUIRED for remote modules.
   * Used by SlotRenderer to group widgets and apply shared providers.
   */
  moduleId: string;
  component: string;
  priority: number;
  localComponent: React.ComponentType<any>;
  defaultProps?: Record<string, any>;
  showWhen?: {
    entityType?: string[];
    layerActive?: string[];
  };
}

export type SlotType = 'layer-toggle' | 'context-panel' | 'bottom-panel' | 'entity-tree' | 'map-layer';

export type ModuleViewerSlots = Record<SlotType, SlotWidgetDefinition[]> & {
  moduleProvider?: React.ComponentType<{ children: React.ReactNode }>;
};

/**
 * LIDAR Module Slots Configuration
 *
 * All widgets explicitly declare moduleId: 'lidar' so the host
 * correctly groups them and applies the LidarProvider context.
 */
export const lidarSlots: ModuleViewerSlots = {
  'map-layer': [
    {
      id: 'lidar-cesium-layer',
      moduleId: MODULE_ID,
      component: 'LidarLayer',
      priority: 10,
      localComponent: LidarLayer
    }
  ],
  'layer-toggle': [
    {
      id: 'lidar-layer-toggle',
      moduleId: MODULE_ID,
      component: 'LidarLayerToggle',
      priority: 10,
      localComponent: LidarLayerToggle,
      showWhen: { entityType: ['AgriParcel'] }
    }
  ],
  'context-panel': [
    {
      id: 'lidar-layer-control',
      moduleId: MODULE_ID,
      component: 'LidarLayerControl',
      priority: 15,
      localComponent: LidarLayerControl,
      showWhen: { entityType: ['AgriParcel'] }
    },
    {
      id: 'lidar-config',
      moduleId: MODULE_ID,
      component: 'LidarConfig',
      priority: 25,
      localComponent: LidarConfig,
      defaultProps: { mode: 'panel' },
      showWhen: { entityType: ['AgriParcel'] }
    }
  ],
  'bottom-panel': [],
  'entity-tree': [],

  // Host's SlotRenderer wraps all widgets from this module with LidarProvider
  moduleProvider: LidarProvider
};

/**
 * Export as viewerSlots for host integration
 */
export const viewerSlots = lidarSlots;
export default lidarSlots;
