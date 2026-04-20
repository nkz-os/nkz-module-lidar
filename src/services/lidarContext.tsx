/**
 * LIDAR Context - Enhanced Module State Management
 *
 * Manages:
 * - Selected entity/parcel (synced with host via useViewer)
 * - Active layer and tileset
 * - Processing job state
 * - Color mode for visualization
 */

import React, { createContext, useContext, useState, ReactNode, useCallback, useEffect, useRef } from 'react';
import { useViewer } from '../sdk';
import { lidarApi, JobStatus, Layer, ProcessingConfig, DEFAULT_PROCESSING_CONFIG } from './api';
import type { GeoJSONGeometry } from '../types';

// ============================================================================
// Cross-Provider Sync Events
// ============================================================================
// When multiple LidarProvider instances exist (one per slot: context-panel,
// map-layer, layer-toggle), they each have independent React state.
// These custom events keep critical state synchronized across instances.
const SYNC_EVENT = 'lidar:sync';
const COLORMODE_EVENT = 'lidar:colormode';

/**
 * Convert GeoJSON geometry to WKT string
 */
function geoJsonToWkt(geojson: GeoJSONGeometry): string | null {
  if (!geojson || !geojson.type) return null;

  const formatCoord = (coord: number[]) => `${coord[0]} ${coord[1]}`;
  const formatRing = (ring: number[][]) => ring.map(formatCoord).join(', ');

  switch (geojson.type) {
    case 'Point':
      return `POINT(${formatCoord(geojson.coordinates)})`;
    case 'LineString':
      return `LINESTRING(${formatRing(geojson.coordinates)})`;
    case 'Polygon': {
      const rings = geojson.coordinates.map((ring: number[][]) => `(${formatRing(ring)})`).join(', ');
      return `POLYGON(${rings})`;
    }
    case 'MultiPolygon': {
      const polys = geojson.coordinates.map((poly: number[][][]) =>
        `(${poly.map((ring: number[][]) => `(${formatRing(ring)})`).join(', ')})`
      ).join(', ');
      return `MULTIPOLYGON(${polys})`;
    }
    default:
      return null;
  }
}

// ============================================================================
// Types
// ============================================================================

export type ColorMode = 'height' | 'ndvi' | 'rgb' | 'classification';

interface LidarContextType {
  // Entity Selection
  selectedEntityId: string | null;
  selectedEntityGeometry: string | null; // WKT
  isLoadingMetadata: boolean;
  setSelectedEntityId: (id: string | null) => void;
  setSelectedEntityGeometry: (wkt: string | null) => void;

  // Layer State
  selectedLayerId: string | null;
  activeTilesetUrl: string | null;
  setSelectedLayerId: (id: string | null) => void;
  setActiveTilesetUrl: (url: string | null) => void;

  // Visualization
  colorMode: ColorMode;
  setColorMode: (mode: ColorMode) => void;
  showTrees: boolean;
  setShowTrees: (show: boolean) => void;

  // Processing
  isProcessing: boolean;
  processingJob: JobStatus | null;
  processingConfig: ProcessingConfig;
  setProcessingConfig: (config: ProcessingConfig) => void;
  startProcessing: () => Promise<void>;

  // Coverage
  hasCoverage: boolean | null;
  checkCoverage: () => Promise<boolean>;

  // Layers
  layers: Layer[];
  refreshLayers: () => Promise<void>;
  deleteLayer: (layerId: string) => Promise<void>;

  // Reset
  resetContext: () => void;
}

const LidarContext = createContext<LidarContextType | undefined>(undefined);

// ============================================================================
// Provider Component
// ============================================================================

export const LidarProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // Unique ID for this provider instance (to ignore own sync events)
  const providerIdRef = useRef(Math.random().toString(36).slice(2));

  // Get entity selection from host via SDK
  const viewer = useViewer();
  
  // Track selected ID to avoid redundant re-fetches
  const lastProcessedIdRef = useRef<string | null>(null);

  // Entity geometry (fetched when entity changes)
  const [selectedEntityGeometry, setSelectedEntityGeometry] = useState<string | null>(null);
  const [isLoadingMetadata, setIsLoadingMetadata] = useState(false);

  // Layer state
  const [selectedLayerId, setSelectedLayerId] = useState<string | null>(null);
  const [activeTilesetUrl, setActiveTilesetUrl] = useState<string | null>(null);
  const [layers, setLayers] = useState<Layer[]>([]);

  // Visualization state
  const [colorMode, setColorMode] = useState<ColorMode>('height');
  const [showTrees, setShowTrees] = useState(false);

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingJob, setProcessingJob] = useState<JobStatus | null>(null);
  const [processingConfig, setProcessingConfig] = useState<ProcessingConfig>(DEFAULT_PROCESSING_CONFIG);

  // Coverage state
  const [hasCoverage, setHasCoverage] = useState<boolean | null>(null);

  // Sync with host viewer context - fetch geometry when entity changes
  useEffect(() => {
    const fetchMetadata = async () => {
      const entityId = viewer.selectedEntityId;
      
      // Avoid redundant fetches if ID hasn't changed
      if (entityId === lastProcessedIdRef.current) return;
      lastProcessedIdRef.current = entityId;

      if (!entityId) {
        setSelectedEntityGeometry(null);
        setSelectedLayerId(null);
        setActiveTilesetUrl(null);
        setHasCoverage(null);
        setProcessingJob(null);
        return;
      }

      // Reset state for new valid entity
      setSelectedLayerId(null);
      setActiveTilesetUrl(null);
      setHasCoverage(null);
      setProcessingJob(null);
      setIsLoadingMetadata(true);

      try {
        // Retrieve tenant and auth from host context
        const auth = (window as any).__nekazariAuthContext;
        const tenantId = auth?.tenantId;
        const contextUrl = auth?.contextUrl || 'https://uri.fiware.org/ns/context.jsonld';

        const headers: HeadersInit = {
          'Accept': 'application/ld+json',
        };
        
        // Ensure NGSI-LD tenant propagation
        if (tenantId) {
          headers['NGSILD-Tenant'] = tenantId;
          headers['X-Tenant-ID'] = tenantId;
        }
        
        // Include Link header for proper context resolution
        headers['Link'] = `<${contextUrl}>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"`;

        const response = await fetch(`/ngsi-ld/v1/entities/${encodeURIComponent(entityId)}`, {
          headers,
          credentials: 'include',
        });

        if (response.ok) {
          const entity = await response.json();
          // location can be in 'location' (NGSI-LD) or 'location.value' (normalized)
          const location = entity.location?.value || entity.location;
          if (location) {
            const wkt = geoJsonToWkt(location as GeoJSONGeometry);
            setSelectedEntityGeometry(wkt);
          }
        } else {
          console.warn(`[LidarContext] Failed to fetch entity metadata: ${response.status}`);
        }
      } catch (error) {
        console.error('[LidarContext] Exception fetching entity geometry:', error);
      } finally {
        setIsLoadingMetadata(false);
      }
    };

    fetchMetadata();
  }, [viewer.selectedEntityId, viewer.selectedEntityType]);

  // Wrapper for selectEntity to match our interface (just id, not id + type)
  const setSelectedEntityId = useCallback((id: string | null) => {
    viewer.selectEntity(id, id ? 'AgriParcel' : null);
  }, [viewer]);

  // Refresh layers list
  const refreshLayers = useCallback(async () => {
    if (!viewer.selectedEntityId) {
      setLayers([]);
      return;
    }

    try {
      const fetchedLayers = await lidarApi.getLayers(viewer.selectedEntityId);
      setLayers(fetchedLayers);

      // Auto-select first layer if available
      if (fetchedLayers.length > 0 && !selectedLayerId) {
        setSelectedLayerId(fetchedLayers[0].id);
        setActiveTilesetUrl(fetchedLayers[0].tileset_url);
      }
    } catch (error) {
      console.error('[LidarContext] Failed to refresh layers:', error);
    }
  }, [viewer.selectedEntityId, selectedLayerId]);

  // Notify other LidarProvider instances to re-fetch layers
  const notifyOtherProviders = useCallback(() => {
    window.dispatchEvent(new CustomEvent(SYNC_EVENT, {
      detail: { providerId: providerIdRef.current }
    }));
  }, []);

  // Listen for sync events from other provider instances
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail.providerId === providerIdRef.current) return;
      const entityId = viewer.selectedEntityId;
      if (entityId) {
        lidarApi.getLayers(entityId).then(fetchedLayers => {
          setLayers(fetchedLayers);
          if (fetchedLayers.length > 0) {
            setSelectedLayerId(fetchedLayers[0].id);
            setActiveTilesetUrl(fetchedLayers[0].tileset_url);
          } else {
            setSelectedLayerId(null);
            setActiveTilesetUrl(null);
          }
        }).catch(() => {});
      }
    };
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, [viewer.selectedEntityId]);

  // Listen for color mode changes from other provider instances
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail.providerId === providerIdRef.current) return;
      setColorMode(detail.mode);
    };
    window.addEventListener(COLORMODE_EVENT, handler);
    return () => window.removeEventListener(COLORMODE_EVENT, handler);
  }, []);

  // Delete a layer
  const deleteLayerFn = useCallback(async (layerId: string) => {
    await lidarApi.deleteLayer(layerId);
    // If deleted layer was active, clear it
    if (selectedLayerId === layerId) {
      setSelectedLayerId(null);
      setActiveTilesetUrl(null);
    }
    await refreshLayers();
    notifyOtherProviders();
  }, [selectedLayerId, refreshLayers, notifyOtherProviders]);

  // Refresh layers when entity changes
  useEffect(() => {
    if (viewer.selectedEntityId) {
      refreshLayers();
    }
  }, [viewer.selectedEntityId, refreshLayers]);

  // Check coverage when geometry is available
  const checkCoverage = useCallback(async (): Promise<boolean> => {
    if (!selectedEntityGeometry) {
      setHasCoverage(false);
      return false;
    }

    try {
      const response = await lidarApi.checkCoverage(selectedEntityGeometry);
      setHasCoverage(response.has_coverage);
      return response.has_coverage;
    } catch (error) {
      console.error('[LidarContext] Coverage check failed:', error);
      setHasCoverage(false);
      return false;
    }
  }, [selectedEntityGeometry]);


  // Start processing job
  const startProcessing = useCallback(async () => {
    if (!viewer.selectedEntityId || !selectedEntityGeometry) {
      throw new Error('No entity selected');
    }

    setIsProcessing(true);
    setProcessingJob(null);

    try {
      const response = await lidarApi.startProcessing({
        parcel_id: viewer.selectedEntityId,
        parcel_geometry_wkt: selectedEntityGeometry,
        config: processingConfig,
      });

      // Poll for completion
      const finalStatus = await lidarApi.pollJobStatus(
        response.job_id,
        (status) => {
          setProcessingJob(status);
        }
      );

      // Update with final results
      if (finalStatus.tileset_url) {
        setActiveTilesetUrl(finalStatus.tileset_url);
        await refreshLayers();
        notifyOtherProviders();
      }
    } catch (error) {
      console.error('[LidarContext] Processing failed:', error);
      throw error;
    } finally {
      setIsProcessing(false);
    }
  }, [viewer.selectedEntityId, selectedEntityGeometry, processingConfig, refreshLayers, notifyOtherProviders]);

  // Color mode setter with cross-provider sync
  const setColorModeWithSync = useCallback((mode: ColorMode) => {
    setColorMode(mode);
    window.dispatchEvent(new CustomEvent(COLORMODE_EVENT, {
      detail: { providerId: providerIdRef.current, mode }
    }));
  }, []);

  // Reset all state (except entity selection which comes from host)
  const resetContext = useCallback(() => {
    viewer.selectEntity(null);
    setSelectedEntityGeometry(null);
    setSelectedLayerId(null);
    setActiveTilesetUrl(null);
    setLayers([]);
    setColorMode('height');
    setShowTrees(false);
    setIsProcessing(false);
    setProcessingJob(null);
    setHasCoverage(null);
  }, [viewer]);

  return (
    <LidarContext.Provider
      value={{
        selectedEntityId: viewer.selectedEntityId,
        selectedEntityGeometry,
        isLoadingMetadata,
        setSelectedEntityId,
        setSelectedEntityGeometry,
        selectedLayerId,
        activeTilesetUrl,
        setSelectedLayerId,
        setActiveTilesetUrl,
        colorMode,
        setColorMode: setColorModeWithSync,
        showTrees,
        setShowTrees,
        isProcessing,
        processingJob,
        processingConfig,
        setProcessingConfig,
        startProcessing,
        hasCoverage,
        checkCoverage,
        layers,
        refreshLayers,
        deleteLayer: deleteLayerFn,
        resetContext,
      }}
    >
      {children}
    </LidarContext.Provider>
  );
};

// ============================================================================
// Hook
// ============================================================================

export const useLidarContext = () => {
  const context = useContext(LidarContext);
  if (context === undefined) {
    throw new Error('useLidarContext must be used within a LidarProvider');
  }
  return context;
};
