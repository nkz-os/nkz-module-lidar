/**
 * LIDAR Layer - Cesium 3D Tiles Integration
 *
 * Features:
 * - Loads 3D Tiles point clouds from tileset URL
 * - Eye Dome Lighting (EDL) for depth perception
 * - Dynamic styling (height, NDVI, classification)
 * - Performance optimization with screen space error
 */

import React, { useEffect, useRef, useCallback } from 'react';
import { useLidarContext, ColorMode } from '../../services/lidarContext';

/* eslint-disable @typescript-eslint/no-explicit-any */
// Cesium types are loaded globally by the host at runtime.
// We use `any` here because Cesium's type definitions are not bundled with this module.
type CesiumViewerType = any;
type CesiumTilesetType = any;

interface LidarLayerProps {
  viewer?: CesiumViewerType;
}

// Color ramps for different visualization modes
const COLOR_RAMPS: Record<string, string> = {
  // Height: Blue (low) -> Green -> Yellow -> Red (high)
  height: `
    var height = \${POSITION}[2];
    var normalized = clamp((height - 0.0) / 50.0, 0.0, 1.0);
    color(
      mix(vec3(0.0, 0.0, 1.0), vec3(1.0, 0.0, 0.0), normalized),
      1.0
    )
  `,

  // NDVI: Red (unhealthy) -> Yellow -> Green (healthy)
  ndvi: `
    var ndvi = \${NDVI};
    var r = (ndvi < 0.5) ? 1.0 : (1.0 - ndvi) * 2.0;
    var g = (ndvi > 0.5) ? 1.0 : ndvi * 2.0;
    color(r, g, 0.0, 1.0)
  `,

  // RGB: Use original point colors
  rgb: `
    color(\${COLOR})
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

export const LidarLayer: React.FC<LidarLayerProps> = ({ viewer }) => {
  const { activeTilesetUrl, colorMode } = useLidarContext();
  const tilesetRef = useRef<CesiumTilesetType | null>(null);

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
    if (!viewer) return;

    // @ts-ignore - Cesium is loaded globally by the host
    const Cesium = window.Cesium;
    if (!Cesium) return;

    // Cleanup previous tileset
    if (tilesetRef.current) {
      viewer.scene.primitives.remove(tilesetRef.current);
      tilesetRef.current = null;
    }

    if (!activeTilesetUrl) return;

    const loadTileset = async () => {
      try {
        let tileset: CesiumTilesetType;

        // Use fromUrl for newer Cesium versions, fallback to constructor
        if (Cesium.Cesium3DTileset.fromUrl) {
          tileset = await Cesium.Cesium3DTileset.fromUrl(activeTilesetUrl, {
            maximumScreenSpaceError: 8,
            maximumMemoryUsage: 1024,
            dynamicScreenSpaceError: true,
            dynamicScreenSpaceErrorDensity: 0.00278,
            dynamicScreenSpaceErrorFactor: 4.0,
          });
        } else {
          tileset = new Cesium.Cesium3DTileset({
            url: activeTilesetUrl,
            maximumScreenSpaceError: 8,
          });
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
        }
      } catch (error) {
        console.error('[LidarLayer] Error loading 3D Tiles:', error);
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

  // This component doesn't render visible DOM elements
  return null;
};

export default LidarLayer;
