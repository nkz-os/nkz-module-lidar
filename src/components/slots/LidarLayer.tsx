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

/** Build a dynamic height-colorization expression using actual Z range. */
function buildHeightExpression(zMin: number, zMax: number): string {
  const span = zMax - zMin || 1;
  // Local Z values from py3dtiles .pnts are ECEF / 100 — use raw local values.
  // Normalize Z into 0-1 range and interpolate blue→green→red.
  // eslint-disable-next-line no-template-curly-in-string
  return `
    mix(
      mix(color('blue'), color('green'), clamp((\${POSITION}[2] - ${zMin}) / (${span} * 0.5), 0.0, 1.0)),
      color('red'),
      clamp(((\${POSITION}[2] - ${zMin}) / ${span} - 0.5) * 2.0, 0.0, 1.0)
    )
  `;
}

const COLOR_RAMPS: Record<string, StyleColor> = {
  // Height: blue (low) → green (mid) → red (high).
  // The default expression below is a fallback for layers without zMin/zMax.
  // LidarLayer.tsx overrides it dynamically via buildHeightExpression().
  height: `
    mix(
      mix(color('blue'), color('green'), clamp((\${POSITION}[2] - 2.0) / 2.0, 0.0, 1.0)),
      color('red'),
      clamp((\${POSITION}[2] - 3.0) / 2.0, 0.0, 1.0)
    )
  `,

  // NDVI: red (unhealthy) → yellow (neutral) → green (healthy).
  // Requires NDVI dimension in batch table (only present when ndvi_source_url
  // was provided during processing). Falls back to green when absent.
  ndvi: `
    \${NDVI} < 0.5
      ? mix(color('red'), color('yellow'), clamp(\${NDVI} * 2.0, 0.0, 1.0))
      : mix(color('yellow'), color('green'), clamp((\${NDVI} - 0.5) * 2.0, 0.0, 1.0))
  `,

  // RGB: native point colors as preserved by py3dtiles convert (default).
  rgb: '${COLOR}',

  // Classification: standard ASPRS LAS class palette. py3dtiles is invoked
  // with --classification so the Classification dimension reaches the
  // batch table. If input .laz lacks proper classification, all points
  // fall into the 'true' catch-all (lightgray).
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
  void useTheme();

  // Get viewer from host context as fallback (host SlotRenderer doesn't pass viewer prop)
  const contextViewer = useCesiumViewer();
  const viewer = viewerProp || contextViewer;

  // Extract Z range from active layer for dynamic height colorization
  const activeLayer = layers.find((l: any) => l.id === selectedLayerId) ?? layers[0];
  const layerZMin: number | undefined = activeLayer?.z_min ?? undefined;
  const layerZMax: number | undefined = activeLayer?.z_max ?? undefined;

  /**
   * Create style expression for current color mode.
   *
   * For height mode, zMin/zMax (from layer metadata) are used to normalize
   * the color ramp across the actual point cloud vertical extent. When
   * unavailable, a sensible default range of 2-5 local Z units is used.
   */
  const createStyle = useCallback((mode: ColorMode, zMin?: number, zMax?: number) => {
    // @ts-ignore - Cesium is loaded globally by the host
    const Cesium = window.Cesium;
    if (!Cesium) return null;

    try {
      let color: StyleColor = COLOR_RAMPS[mode] || COLOR_RAMPS.height;
      if (mode === 'height' && zMin != null && zMax != null && zMax > zMin) {
        color = buildHeightExpression(zMin, zMax);
      }
      return new Cesium.Cesium3DTileStyle({
        color,
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
    // Max concurrent tilesets: scope 'all' loads at most 3 to avoid GPU VRAM exhaustion.
    const MAX_TILESETS_ALL = 3;
    if (layerScope === 'all') {
      layers.forEach((l: any) => {
        if (l && l.tileset_url) targets.push({ id: l.id, url: l.tileset_url });
      });
      if (targets.length > MAX_TILESETS_ALL) targets.length = MAX_TILESETS_ALL;
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
            maximumMemoryUsage: 256,
            dynamicScreenSpaceError: true,
            dynamicScreenSpaceErrorDensity: 0.00278,
            dynamicScreenSpaceErrorFactor: 1.5,
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

          const style = createStyle(colorMode, layerZMin, layerZMax);
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
        // Deliberately do NOT auto-flyTo the tileset.  The user chooses
        // when to zoom via the viewer controls.  Auto-flying steals the
        // camera and, combined with regional PNOA outages, makes the
        // entire map appear broken.
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
  }, [viewer, layerScope, layerVisible, activeTilesetUrl, layers, selectedLayerId]);

  /**
   * Update style when color mode or Z range changes, without reloading tilesets.
   * Keeping the Cesium3DTileset alive avoids the "this._root is undefined" crash
   * that occurs when a tileset is removed from scene.primitives mid-render.
   */
  useEffect(() => {
    if (tilesetRefs.current.length === 0) return;
    const style = createStyle(colorMode, layerZMin, layerZMax);
    if (!style) return;
    tilesetRefs.current.forEach(ts => { ts.style = style; });
  }, [colorMode, createStyle, layerZMin, layerZMax]);

  /**
   * Update modelMatrix when height offset changes, without reloading tilesets.
   * Same rationale as the style effect above: avoid destroy+recreate crash.
   */
  useEffect(() => {
    if (tilesetRefs.current.length === 0) return;
    const Cesium = (window as any).Cesium;
    if (!Cesium) return;
    tilesetRefs.current.forEach(ts => {
      try {
        if (!ts.boundingSphere || ts.isDestroyed?.()) return;
        const center = ts.boundingSphere.center;
        const cartographic = Cesium.Cartographic.fromCartesian(center);
        const offsetCenter = Cesium.Cartesian3.fromRadians(
          cartographic.longitude,
          cartographic.latitude,
          cartographic.height + heightOffset
        );
        const translation = Cesium.Cartesian3.subtract(offsetCenter, center, new Cesium.Cartesian3());
        ts.modelMatrix = Cesium.Matrix4.fromTranslation(translation);
      } catch (e) {
        console.warn('[LidarLayer] Could not update height offset:', e);
      }
    });
  }, [heightOffset]);

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
