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
import { useTheme } from '@nekazari/design-tokens';
import { Spinner } from '@nekazari/ui-kit';
import { useLidarContext, ColorMode } from '../../services/lidarContext';

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

// Color ramps for different visualization modes.
//
// The Cesium 3D Tiles Styling Language is a single-expression subset.
// It accepts color() / rgba() / hsla() constructors, mix(), clamp(), the
// ternary operator and the conditions[] form. It does NOT accept variable
// declarations (var/float/vec3/vec4) or block statements (if/else),
// despite their resemblance to GLSL or JavaScript. Earlier revisions used
// GLSL-style code and silently failed to parse, leaving every tileset
// rendered with the default white style.
type StyleColor = string | { conditions: [string, string][] };

const COLOR_RAMPS: Record<string, StyleColor> = {
  // Height: blue (low) → green (mid) → red (high), measured along the
  // tile-local Z axis clamped to a 0–50 m relative window.
  height: `
    \${POSITION}[2] < 25.0
      ? mix(color('blue'), color('green'), clamp(\${POSITION}[2] / 25.0, 0.0, 1.0))
      : mix(color('green'), color('red'), clamp((\${POSITION}[2] - 25.0) / 25.0, 0.0, 1.0))
  `,

  // NDVI: red (unhealthy) → yellow (neutral) → green (healthy).
  // Negative NDVI is clamped to 0 to keep the gradient monotonic.
  ndvi: `
    \${NDVI} < 0.5
      ? mix(color('red'), color('yellow'), clamp(\${NDVI} * 2.0, 0.0, 1.0))
      : mix(color('yellow'), color('green'), clamp((\${NDVI} - 0.5) * 2.0, 0.0, 1.0))
  `,

  // RGB: native point colors as preserved by py3dtiles convert (default).
  rgb: '${COLOR}',

  // Classification: standard ASPRS LAS class palette. py3dtiles is invoked
  // with --classification so the Classification dimension reaches the
  // batch table.
  classification: {
    conditions: [
      ['${Classification} === 2', "color('saddlebrown')"],
      ['${Classification} >= 3 && ${Classification} <= 5', "color('forestgreen')"],
      ['${Classification} === 6', "color('crimson')"],
      ['${Classification} === 9', "color('royalblue')"],
      ['true', "color('lightgray')"],
    ],
  },
};

export const LidarLayer: React.FC<LidarLayerProps> = ({ viewer: viewerProp }) => {
  const { activeTilesetUrl, colorMode, heightOffset } = useLidarContext();
  const tilesetRef = useRef<CesiumTilesetType | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const theme = useTheme();

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
        pointSize: 5,
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

        // Apply height offset to compensate for orthometric→ellipsoidal datum difference
        if (heightOffset !== 0 && tileset.boundingSphere) {
          try {
            const center = tileset.boundingSphere.center;
            const cartographic = Cesium.Cartographic.fromCartesian(center);
            const offsetCenter = Cesium.Cartesian3.fromRadians(
              cartographic.longitude,
              cartographic.latitude,
              cartographic.height + heightOffset
            );
            const translation = Cesium.Cartesian3.subtract(offsetCenter, center, new Cesium.Cartesian3());
            tileset.modelMatrix = Cesium.Matrix4.fromTranslation(translation);
          } catch (e) {
            console.warn('[LidarLayer] Could not apply height offset:', e);
          }
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
      <div className="absolute bottom-4 left-4 z-50 bg-nkz-surface backdrop-blur-sm rounded-nkz-md px-nkz-stack py-nkz-inline shadow-nkz-lg border border-nkz-border flex items-center gap-nkz-inline">
        <Spinner size="sm" />
        <span className="text-nkz-sm text-nkz-text-primary">Loading point cloud...</span>
      </div>
    );
  }

  // Show error if Cesium or loading fails
  if (loadError) {
    return (
      <div className="absolute bottom-4 left-4 z-50 bg-nkz-danger-soft rounded-nkz-md px-nkz-stack py-nkz-inline shadow-nkz-lg border border-nkz-danger">
        <span className="text-nkz-sm text-nkz-danger-strong">{loadError}</span>
      </div>
    );
  }

  return null;
};

export default LidarLayer;
