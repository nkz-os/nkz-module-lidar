/**
 * LIDAR Context - Enhanced Module State Management
 *
 * Manages:
 * - Selected entity/parcel (synced with host via useViewer)
 * - Active layer and tileset
 * - Processing job state
 * - Color mode for visualization
 */

import React, { createContext, useContext, useState, ReactNode, useCallback, useEffect } from 'react';
import { useViewer } from '../sdk';
import { lidarApi, JobStatus, Layer, ProcessingConfig, DEFAULT_PROCESSING_CONFIG } from './api';
import type { GeoJSONGeometry } from '../types';

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
  // Get entity selection from host via SDK
  const viewer = useViewer();

  // Entity geometry (fetched when entity changes)
  const [selectedEntityGeometry, setSelectedEntityGeometry] = useState<string | null>(null);
  const [, setIsLoadingGeometry] = useState(false);

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
    const fetchGeometry = async () => {
      if (!viewer.selectedEntityId || viewer.selectedEntityType !== 'AgriParcel') {
        setSelectedEntityGeometry(null);
        setSelectedLayerId(null);
        setActiveTilesetUrl(null);
        setHasCoverage(null);
        setProcessingJob(null);
        return;
      }

      // Reset state for new entity
      setSelectedLayerId(null);
      setActiveTilesetUrl(null);
      setHasCoverage(null);
      setProcessingJob(null);
      setIsLoadingGeometry(true);

      try {
        // Fetch entity geometry from Context Broker
        const auth = window.__nekazariAuth;
        const headers: HeadersInit = {
          'Accept': 'application/ld+json',
        };
        if (auth?.token) {
          headers['Authorization'] = `Bearer ${auth.token}`;
        }
        if (auth?.tenantId) {
          headers['NGSILD-Tenant'] = auth.tenantId;
        }

        const response = await fetch(`/ngsi-ld/v1/entities/${encodeURIComponent(viewer.selectedEntityId)}`, {
          headers,
        });

        if (response.ok) {
          const entity = await response.json();
          const location = entity.location?.value;
          if (location) {
            const wkt = geoJsonToWkt(location as GeoJSONGeometry);
            setSelectedEntityGeometry(wkt);
          }
        }
      } catch (error) {
        console.error('[LidarContext] Error fetching entity geometry:', error);
      } finally {
        setIsLoadingGeometry(false);
      }
    };

    fetchGeometry();
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

  // Delete a layer
  const deleteLayerFn = useCallback(async (layerId: string) => {
    await lidarApi.deleteLayer(layerId);
    // If deleted layer was active, clear it
    if (selectedLayerId === layerId) {
      setSelectedLayerId(null);
      setActiveTilesetUrl(null);
    }
    await refreshLayers();
  }, [selectedLayerId, refreshLayers]);

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
      }
    } catch (error) {
      console.error('[LidarContext] Processing failed:', error);
      throw error;
    } finally {
      setIsProcessing(false);
    }
  }, [viewer.selectedEntityId, selectedEntityGeometry, processingConfig, refreshLayers]);

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
        setSelectedEntityId,
        setSelectedEntityGeometry,
        selectedLayerId,
        activeTilesetUrl,
        setSelectedLayerId,
        setActiveTilesetUrl,
        colorMode,
        setColorMode,
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
