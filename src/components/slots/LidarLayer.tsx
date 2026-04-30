/**
 * LIDAR Layer - Cesium 3D Tiles Integration
 *
 * Features:
 * - Loads 3D Tiles point clouds from tileset URL
 * - Eye Dome Lighting (EDL) for depth perception
 * - Dynamic styling (height, NDVI, classification)
 * - Performance optimization with screen space error
 */

import React, { useEffect, useRef, useCallback, useState } from 'react';
import { useLidarContext, ColorMode } from '../../services/lidarContext';
import { Loader2 } from 'lucide-react';

/* eslint-disable @typescript-eslint/no-explicit-any */
// Cesium types are loaded globally by the host at runtime.
// We use `any` here because Cesium's type definitions are not bundled with this module.
type CesiumViewerType = any;
type CesiumTilesetType = any;

/**
 * Get the Cesium viewer from the host's ViewerContext.
 * The host exposes window.__nekazariViewerContextInstance which holds cesiumViewer.
 * This is the canonical way for IIFE modules to access the Cesium viewer.
 */
function useCesiumViewer(): CesiumViewerType | null {
  try {
    const React = (window as any).React;
    const ctx = React.useContext((window as any).__nekazariViewerContextInstance);
    return ctx?.cesiumViewer ?? null;
  } catch {
    return null;
  }
}

interface LidarLayerProps {
  viewer?: CesiumViewerType;
}

// Color ramps for different visualization modes
const COLOR_RAMPS: Record<string, string> = {
  // Height: Blue (low) → Cyan → Green → Yellow → Red (high)
  height: `
    float t = clamp((${POSITION}[2] - 0.0) / 50.0, 0.0, 1.0);
    float r = t < 0.5 ? 0.0 : (t - 0.5) * 2.0;
    float g = t < 0.5 ? t * 2.0 : 2.0 - t * 2.0;
    float b = 1.0 - t;
    color(r, g, b, 1.0)
  `,

  // NDVI: Red (unhealthy) → Yellow → Green (healthy)
  ndvi: `
    float ndvi = clamp(${NDVI}, -1.0, 1.0);
    float r = clamp(1.0 - ndvi, 0.0, 1.0);
    float g = clamp(ndvi, 0.0, 1.0);
    color(r, g, 0.0, 1.0)
  `,

  // RGB: True color from point cloud
  rgb: `
    vec4 c = ${COLOR};
    color(c.r, c.g, c.b, 1.0)
  `,

  // Classification: Standard LiDAR classification colors
  classification: `
    var class = \${Classification};
    if (class == 2.0) { // Ground
      color(0.6, 0.4, 0.2, 1.0)
    } else if (class == 3.0 || class == 4.0 || class == 5.0) { // Vegetation
      color(0.0, 0.8, 0.2, 1.0)
    } else if (class == 6.0) { // Building
      color(0.8, 0.0, 0.0, 1.0)
    } else if (class == 9.0) { // Water
      color(0.0, 0.4, 0.8, 1.0)
    } else {
      color(0.5, 0.5, 0.5, 1.0)
    }
  `,
};

export const LidarLayer: React.FC<LidarLayerProps> = ({ viewer: viewerProp }) => {
  const { activeTilesetUrl, colorMode } = useLidarContext();
  const tilesetRef = useRef<CesiumTilesetType | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Get viewer from host context as fallback (host SlotRenderer doesn't pass viewer prop)
  const contextViewer = useCesiumViewer();
  const viewer = viewerProp || contextViewer;

  /**
   * Create style expression for current color mode
   */
  const createStyle = useCallback((mode: ColorMode) => {
    // @ts-ignore - Cesium is loaded globally by the host
    const Cesium = window.Cesium;
    if (!Cesium) return null;

    try {
      return new Cesium.Cesium3DTileStyle({
        color: COLOR_RAMPS[mode] || COLOR_RAMPS.height,
        pointSize: 3,
      });
    } catch (error) {
      console.error('[LidarLayer] Error creating style:', error);
      return null;
    }
  }, []);

  /**
   * Load 3D Tiles tileset
   */
  useEffect(() => {
    console.log('[LidarLayer] viewer:', !!viewer, 'url:', activeTilesetUrl);
    if (!viewer) { console.warn('[LidarLayer] No viewer prop'); return; }

    // @ts-ignore - Cesium is loaded globally by the host
    const Cesium = window.Cesium;
    if (!Cesium) {
      console.warn('[LidarLayer] Cesium not available');
      setLoadError('CesiumJS not available');
      return;
    }

    // Cleanup previous tileset
    if (tilesetRef.current) {
      viewer.scene.primitives.remove(tilesetRef.current);
      tilesetRef.current = null;
    }

    if (!activeTilesetUrl) {
      console.log('[LidarLayer] No active tileset URL');
      setIsLoading(false);
      setLoadError(null);
      return;
    }

    console.log('[LidarLayer] Loading:', activeTilesetUrl.substring(0, 80) + '...');
    setIsLoading(true);

    const loadTileset = async () => {
      try {
        let tileset: CesiumTilesetType;
        const options = {
          maximumScreenSpaceError: 8,
          maximumMemoryUsage: 1024,
          dynamicScreenSpaceError: true,
          dynamicScreenSpaceErrorDensity: 0.00278,
          dynamicScreenSpaceErrorFactor: 4.0,
        };

        if (Cesium.Cesium3DTileset.fromUrl) {
          tileset = await Cesium.Cesium3DTileset.fromUrl(activeTilesetUrl, options);
        } else {
          tileset = new Cesium.Cesium3DTileset({ url: activeTilesetUrl, ...options });
        }

        // Add to scene
        viewer.scene.primitives.add(tileset);
        tilesetRef.current = tileset;

        // Apply initial style
        const style = createStyle(colorMode);
        if (style) {
          tileset.style = style;
        }

        // Wait for tileset to load then fly to it
        if (tileset.readyPromise) {
          await tileset.readyPromise;
        }

        if (!viewer.isDestroyed()) {
          viewer.flyTo(tileset, {
            duration: 1.5,
            offset: new Cesium.HeadingPitchRange(
              0,
              Cesium.Math.toRadians(-45),
              1000
            ),
          });
          setIsLoading(false);
        }
      } catch (error) {
        console.error('[LidarLayer] Error loading 3D Tiles:', error);
        setLoadError('Failed to load point cloud');
        setIsLoading(false);
      }
    };

    loadTileset();

    // Cleanup on unmount
    return () => {
      if (tilesetRef.current && viewer && !viewer.isDestroyed()) {
        viewer.scene.primitives.remove(tilesetRef.current);
        tilesetRef.current = null;
      }
    };
  }, [viewer, activeTilesetUrl, createStyle, colorMode]);

  /**
   * Update style when color mode changes
   */
  useEffect(() => {
    if (tilesetRef.current) {
      const style = createStyle(colorMode);
      if (style) {
        tilesetRef.current.style = style;
      }
    }
  }, [colorMode, createStyle]);

  // Show loading indicator while tileset loads
  if (activeTilesetUrl && isLoading) {
    return (
      <div className="absolute bottom-4 left-4 z-50 bg-white/90 backdrop-blur-sm rounded-lg px-3 py-2 shadow-lg border border-slate-200 flex items-center gap-2">
        <Loader2 className="w-4 h-4 text-violet-500 animate-spin" />
        <span className="text-sm text-slate-700">Loading point cloud...</span>
      </div>
    );
  }

  // Show error if Cesium or loading fails
  if (loadError) {
    return (
      <div className="absolute bottom-4 left-4 z-50 bg-red-50 rounded-lg px-3 py-2 shadow-lg border border-red-200">
        <span className="text-sm text-red-700">{loadError}</span>
      </div>
    );
  }

  return null;
};

export default LidarLayer;
