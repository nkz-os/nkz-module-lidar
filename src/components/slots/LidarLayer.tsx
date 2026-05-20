/**
 * LIDAR Layer - Cesium 3D Tiles Integration
 *
 * Features:
 * - Loads 3D Tiles point clouds from tileset URL(s)
 * - Scope 'selected': mounts the currently active tileset only
 * - Scope 'all': mounts one Cesium3DTileset per available layer
 * - Eye Dome Lighting (EDL) for depth perception
 * - Dynamic styling (height, NDVI, classification)
 * - Performance optimization with screen space error (16 when >5 tilesets)
 */

import React, { useContext, useEffect, useRef, useCallback, useState } from 'react';
import { useTheme } from '@nekazari/design-tokens';
import { Spinner } from '@nekazari/ui-kit';
import { useLidarContext, ColorMode } from '../../services/lidarContext';

/* eslint-disable @typescript-eslint/no-explicit-any */
// Cesium types are loaded globally by the host at runtime.
// We use `any` here because Cesium's type definitions are not bundled with this module.
type CesiumViewerType = any;
type CesiumTilesetType = any;

// Stable fallback used when the host has not (yet) exposed its ViewerContext.
// Created once at module load so useContext gets a stable reference.
const FallbackViewerContext = React.createContext<any>(undefined);

// The host exposes its ViewerContext object on window so federated modules can
// subscribe to it with their own React. Module Federation 2.0 makes React a
// shared singleton, so `useContext` from our import sees the same context
// instance the host provides at runtime.
function useCesiumViewer(): CesiumViewerType | null {
  const HostViewerContext = (window as any).__nekazariViewerContextInstance as React.Context<any> | undefined;
  const ctx = useContext(HostViewerContext ?? FallbackViewerContext);
  return ctx?.cesiumViewer ?? null;
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
  const {
    activeTilesetUrl,
    colorMode,
    heightOffset,
    layerVisible,
    layerScope,
    layers,
    selectedLayerId,
  } = useLidarContext();
  const tilesetRefs = useRef<CesiumTilesetType[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  // useTheme kept for parity with original — may be used by future styling extensions
  const _theme = useTheme();

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
   * Load 3D Tiles tilesets — one per target depending on scope.
   */
  useEffect(() => {
    if (!viewer) return;
    const Cesium = (window as any).Cesium;
    if (!Cesium) {
      setLoadError('CesiumJS not available');
      return;
    }

    // Cleanup all prior tilesets
    tilesetRefs.current.forEach(ts => {
      try { viewer.scene.primitives.remove(ts); } catch { /* destroyed */ }
    });
    tilesetRefs.current = [];

    if (!layerVisible) {
      setIsLoading(false);
      setLoadError(null);
      return;
    }

    const targets: { id: string; url: string }[] = [];
    if (layerScope === 'all') {
      layers.forEach((l: any) => {
        if (l && l.tileset_url) targets.push({ id: l.id, url: l.tileset_url });
      });
    } else if (activeTilesetUrl) {
      targets.push({ id: selectedLayerId ?? 'active', url: activeTilesetUrl });
    }

    if (targets.length === 0) {
      setIsLoading(false);
      setLoadError(null);
      return;
    }

    const sse = targets.length > 5 ? 16 : 8;

    setIsLoading(true);
    setLoadError(null);

    let cancelled = false;
    (async () => {
      for (const t of targets) {
        if (cancelled) return;
        try {
          const options = {
            maximumScreenSpaceError: sse,
            maximumMemoryUsage: 1024,
            dynamicScreenSpaceError: true,
            dynamicScreenSpaceErrorDensity: 0.00278,
            dynamicScreenSpaceErrorFactor: 4.0,
          };

          let tileset: CesiumTilesetType;
          if (Cesium.Cesium3DTileset.fromUrl) {
            tileset = await Cesium.Cesium3DTileset.fromUrl(t.url, options);
          } else {
            tileset = new Cesium.Cesium3DTileset({ url: t.url, ...options });
          }

          if (cancelled || viewer.isDestroyed()) {
            try { tileset.destroy?.(); } catch { /* ok */ }
            return;
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

          const style = createStyle(colorMode);
          if (style) tileset.style = style;
          viewer.scene.primitives.add(tileset);
          tilesetRefs.current.push(tileset);
        } catch (err) {
          console.error('[LidarLayer] tileset load failed', t.url, err);
        }
      }

      if (cancelled) return;

      if (tilesetRefs.current.length > 0) {
        setIsLoading(false);
        if (!viewer.isDestroyed()) {
          try {
            // Fly to the first loaded tileset (readyPromise compat)
            const first = tilesetRefs.current[0];
            if (first.readyPromise) await first.readyPromise;
            await viewer.flyTo(first, {
              duration: 1.5,
              offset: new Cesium.HeadingPitchRange(
                0,
                Cesium.Math.toRadians(-45),
                1000
              ),
            });
          } catch { /* ok */ }
        }
      } else {
        setIsLoading(false);
        setLoadError('Failed to load point cloud');
      }
    })();

    return () => {
      cancelled = true;
      tilesetRefs.current.forEach(ts => {
        try {
          if (viewer && !viewer.isDestroyed()) viewer.scene.primitives.remove(ts);
        } catch { /* ok */ }
      });
      tilesetRefs.current = [];
    };
  }, [viewer, layerScope, layerVisible, activeTilesetUrl, layers, selectedLayerId, heightOffset, createStyle, colorMode]);

  /**
   * Update style when color mode changes without reloading tilesets.
   */
  useEffect(() => {
    if (tilesetRefs.current.length === 0) return;
    const style = createStyle(colorMode);
    if (!style) return;
    tilesetRefs.current.forEach(ts => { ts.style = style; });
  }, [colorMode, createStyle]);

  // Show loading indicator while tileset(s) load
  if (layerVisible && isLoading) {
    return (
      <div className="absolute bottom-4 left-4 z-50 bg-white dark:bg-slate-900 rounded-nkz-md px-nkz-stack py-nkz-inline shadow-nkz-lg border border-slate-200 dark:border-slate-700 flex items-center gap-nkz-inline">
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
