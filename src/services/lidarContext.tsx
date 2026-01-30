/**
 * LIDAR Context - Enhanced Module State Management
 * 
 * Manages:
 * - Selected entity/parcel
 * - Active layer and tileset
 * - Processing job state
 * - Color mode for visualization
 */

import React, { createContext, useContext, useState, ReactNode, useCallback, useEffect } from 'react';
import { lidarApi, JobStatus, Layer, ProcessingConfig, DEFAULT_PROCESSING_CONFIG } from './api';

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

  // Reset
  resetContext: () => void;
}

const LidarContext = createContext<LidarContextType | undefined>(undefined);

// ============================================================================
// Provider Component
// ============================================================================

export const LidarProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // Entity state
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [selectedEntityGeometry, setSelectedEntityGeometry] = useState<string | null>(null);

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

  // Listen for entity selection events from Host
  useEffect(() => {
    const handleEntitySelected = (event: CustomEvent<{
      entityId: string | null;
      type?: string;
      geometry?: string; // WKT
    }>) => {
      console.log('[LidarContext] Received entity selection:', event.detail);
      if (event.detail) {
        setSelectedEntityId(event.detail.entityId);
        setSelectedEntityGeometry(event.detail.geometry || null);
        setSelectedLayerId(null);
        setActiveTilesetUrl(null);
        setHasCoverage(null);
        setProcessingJob(null);
      }
    };

    window.addEventListener('nekazari:entity-selected', handleEntitySelected as EventListener);

    // Initial check from global context
    const globalContext = (window as any).__nekazariContext;
    if (globalContext?.selectedEntityId) {
      console.log('[LidarContext] Initializing from global context:', globalContext.selectedEntityId);
      setSelectedEntityId(globalContext.selectedEntityId);
      setSelectedEntityGeometry(globalContext.selectedEntityGeometry || null);
    }

    return () => {
      window.removeEventListener('nekazari:entity-selected', handleEntitySelected as EventListener);
    };
  }, []);

  // Refresh layers when entity changes
  useEffect(() => {
    if (selectedEntityId) {
      refreshLayers();
    }
  }, [selectedEntityId]);

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

  // Refresh layers list
  const refreshLayers = useCallback(async () => {
    if (!selectedEntityId) {
      setLayers([]);
      return;
    }

    try {
      const fetchedLayers = await lidarApi.getLayers(selectedEntityId);
      setLayers(fetchedLayers);

      // Auto-select first layer if available
      if (fetchedLayers.length > 0 && !selectedLayerId) {
        setSelectedLayerId(fetchedLayers[0].id);
        setActiveTilesetUrl(fetchedLayers[0].tileset_url);
      }
    } catch (error) {
      console.error('[LidarContext] Failed to refresh layers:', error);
    }
  }, [selectedEntityId, selectedLayerId]);

  // Start processing job
  const startProcessing = useCallback(async () => {
    if (!selectedEntityId || !selectedEntityGeometry) {
      throw new Error('No entity selected');
    }

    setIsProcessing(true);
    setProcessingJob(null);

    try {
      // Start the job
      const response = await lidarApi.startProcessing({
        parcel_id: selectedEntityId,
        parcel_geometry_wkt: selectedEntityGeometry,
        config: processingConfig,
      });

      console.log('[LidarContext] Processing started:', response);

      // Poll for completion
      const finalStatus = await lidarApi.pollJobStatus(
        response.job_id,
        (status) => {
          console.log('[LidarContext] Job progress:', status);
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
  }, [selectedEntityId, selectedEntityGeometry, processingConfig, refreshLayers]);

  // Reset all state
  const resetContext = useCallback(() => {
    setSelectedEntityId(null);
    setSelectedEntityGeometry(null);
    setSelectedLayerId(null);
    setActiveTilesetUrl(null);
    setLayers([]);
    setColorMode('height');
    setShowTrees(false);
    setIsProcessing(false);
    setProcessingJob(null);
    setHasCoverage(null);
  }, []);

  return (
    <LidarContext.Provider
      value={{
        selectedEntityId,
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

