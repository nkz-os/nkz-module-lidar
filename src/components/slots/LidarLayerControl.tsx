/**
 * LIDAR Layer Control - Premium Control Panel
 * 
 * Features:
 * - Check PNOA coverage with visual feedback
 * - Download from PNOA or upload custom .LAZ file
 * - Configure processing options (colorization, tree detection)
 * - Job progress monitoring with animations
 * - Layer management with premium UI
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Layers,
  Download,
  Upload,
  Settings,
  RefreshCw,
  CheckCircle,
  XCircle,
  Loader2,
  TreeDeciduous,
  Palette,
  Sparkles,
  Cloud,
  Database
} from 'lucide-react';
import { useUIKit } from '../../hooks/useUIKit';
import { useLidarContext, ColorMode } from '../../services/lidarContext';

const COLOR_MODE_OPTIONS: { value: ColorMode; label: string; icon: string; desc: string }[] = [
  { value: 'height', label: 'Altura', icon: '📏', desc: 'Gradiente por elevación' },
  { value: 'ndvi', label: 'NDVI', icon: '🌿', desc: 'Índice de vegetación' },
  { value: 'rgb', label: 'Color', icon: '🎨', desc: 'Colores originales' },
  { value: 'classification', label: 'Clase', icon: '🏷️', desc: 'Clasificación LiDAR' },
];

const LidarLayerControl: React.FC = () => {
  const { Card } = useUIKit();
  const {
    selectedEntityId,
    selectedEntityGeometry,
    activeTilesetUrl,
    colorMode,
    setColorMode,
    isProcessing,
    processingJob,
    processingConfig,
    setProcessingConfig,
    startProcessing,
    hasCoverage,
    checkCoverage,
    layers,
    refreshLayers,
  } = useLidarContext();

  const [showSettings, setShowSettings] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Check coverage when entity is selected
  useEffect(() => {
    if (selectedEntityGeometry && hasCoverage === null) {
      checkCoverage();
    }
  }, [selectedEntityGeometry, hasCoverage, checkCoverage]);

  // =========================================================================
  // Handlers
  // =========================================================================

  const handleStartProcessing = async () => {
    try {
      setUploadError(null);
      await startProcessing();
    } catch (error: any) {
      setUploadError(error.message || 'Error al procesar');
    }
  };

  const handleFileUpload = async (file: File) => {
    // Validate file extension
    if (!file.name.toLowerCase().endsWith('.laz') && !file.name.toLowerCase().endsWith('.las')) {
      setUploadError('Solo se permiten archivos .LAZ o .LAS');
      return;
    }

    // Validate file size (max 500MB)
    const maxSize = 500 * 1024 * 1024;
    if (file.size > maxSize) {
      setUploadError('El archivo es demasiado grande (máx. 500MB)');
      return;
    }

    setIsUploading(true);
    setUploadError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('parcel_id', selectedEntityId || 'unknown');
      if (selectedEntityGeometry) {
        formData.append('geometry_wkt', selectedEntityGeometry);
      }
      formData.append('config', JSON.stringify(processingConfig));

      const auth = (window as any).__nekazariAuth;
      const headers: HeadersInit = {};
      if (auth?.token) {
        headers['Authorization'] = `Bearer ${auth.token}`;
      }

      const response = await fetch('/api/lidar/upload', {
        method: 'POST',
        headers,
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Error al subir el archivo');
      }

      console.log('[LidarLayerControl] Upload started');
      await refreshLayers();
    } catch (error: any) {
      console.error('[LidarLayerControl] Upload error:', error);
      setUploadError(error.message || 'Error al subir el archivo');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) handleFileUpload(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileUpload(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  // =========================================================================
  // Render: No entity selected
  // =========================================================================

  if (!selectedEntityId) {
    return (
      <div className="lidar-card p-6 lidar-slide-in">
        <div className="flex flex-col items-center justify-center gap-3 py-4 text-slate-500">
          <div className="p-3 rounded-full bg-slate-100">
            <Layers className="w-6 h-6 text-slate-400" />
          </div>
          <p className="text-sm font-medium">Selecciona una parcela</p>
          <p className="text-xs text-slate-400">para activar capas LiDAR</p>
        </div>
      </div>
    );
  }

  // =========================================================================
  // Render: Main Control Panel
  // =========================================================================

  return (
    <div className="lidar-card w-80 shadow-lg pointer-events-auto lidar-slide-in overflow-hidden">
      {/* Header with gradient accent */}
      <div className="px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-violet-50 to-cyan-50">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-slate-800 flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-gradient-to-br from-violet-500 to-cyan-500">
              <Layers className="w-4 h-4 text-white" />
            </div>
            LiDAR
          </h3>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className={`p-2 rounded-lg transition-all duration-200 ${showSettings
                ? 'bg-violet-100 text-violet-600'
                : 'hover:bg-slate-100 text-slate-500'
              }`}
            title="Configuración"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* Settings Panel */}
        {showSettings && (
          <div className="p-4 bg-slate-50 rounded-xl space-y-4 border border-slate-200 lidar-slide-in">
            <h4 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-violet-500" />
              Opciones de Procesamiento
            </h4>

            {/* Color Mode */}
            <div>
              <label className="lidar-label flex items-center gap-1 mb-2">
                <Palette className="w-3 h-3" />
                Colorización
              </label>
              <select
                value={processingConfig.colorize_by}
                onChange={(e) => setProcessingConfig({
                  ...processingConfig,
                  colorize_by: e.target.value as ColorMode
                })}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white focus:ring-2 focus:ring-violet-200 focus:border-violet-400 transition-all"
              >
                {COLOR_MODE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.icon} {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Tree Detection Toggle */}
            <label className="flex items-center gap-3 p-3 bg-white rounded-lg border border-slate-200 cursor-pointer hover:border-violet-300 transition-all">
              <input
                type="checkbox"
                checked={processingConfig.detect_trees}
                onChange={(e) => setProcessingConfig({
                  ...processingConfig,
                  detect_trees: e.target.checked
                })}
                className="w-4 h-4 rounded text-violet-600 focus:ring-violet-500"
              />
              <div className="flex items-center gap-2">
                <TreeDeciduous className="w-4 h-4 text-emerald-500" />
                <span className="text-sm text-slate-700">Detectar árboles</span>
              </div>
            </label>

            {/* Tree Detection Options */}
            {processingConfig.detect_trees && (
              <div className="ml-4 pl-4 border-l-2 border-emerald-200 space-y-3 lidar-slide-in">
                <div>
                  <label className="text-xs text-slate-500 block mb-1">Altura mínima (m)</label>
                  <input
                    type="number"
                    value={processingConfig.tree_min_height}
                    onChange={(e) => setProcessingConfig({
                      ...processingConfig,
                      tree_min_height: parseFloat(e.target.value) || 2.0
                    })}
                    min={0.5}
                    max={20}
                    step={0.5}
                    className="w-full border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-emerald-200"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-500 block mb-1">Radio búsqueda (m)</label>
                  <input
                    type="number"
                    value={processingConfig.tree_search_radius}
                    onChange={(e) => setProcessingConfig({
                      ...processingConfig,
                      tree_search_radius: parseFloat(e.target.value) || 3.0
                    })}
                    min={1}
                    max={10}
                    step={0.5}
                    className="w-full border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-emerald-200"
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Processing Status */}
        {isProcessing && processingJob && (
          <div className="p-4 rounded-xl bg-gradient-to-br from-violet-50 to-cyan-50 border border-violet-200 lidar-pulse">
            <div className="flex items-center gap-2 mb-3">
              <Loader2 className="w-5 h-5 text-violet-600 animate-spin" />
              <span className="text-sm font-semibold text-violet-900">
                Procesando...
              </span>
            </div>
            <div className="lidar-progress mb-2">
              <div
                className="lidar-progress-bar"
                style={{ width: `${processingJob.progress}%` }}
              />
            </div>
            <p className="text-xs text-violet-700">
              {processingJob.status_message || 'Procesando nube de puntos...'}
            </p>
          </div>
        )}

        {/* Error Display */}
        {uploadError && (
          <div className="lidar-status lidar-status-error lidar-slide-in">
            <XCircle className="w-4 h-4 flex-shrink-0" />
            <p className="text-xs">{uploadError}</p>
          </div>
        )}

        {/* Active Layer */}
        {activeTilesetUrl && !isProcessing && (
          <div className="space-y-3 lidar-slide-in">
            <div className="p-4 rounded-xl bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-200">
              <div className="flex items-center gap-2 mb-3">
                <div className="lidar-status-dot lidar-status-dot-success" />
                <span className="text-sm font-semibold text-emerald-900">Capa Activa</span>
              </div>

              {/* Color Mode Pills */}
              <div className="flex flex-wrap gap-1.5">
                {COLOR_MODE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setColorMode(opt.value)}
                    className={`lidar-chip ${colorMode === opt.value ? 'lidar-chip-active' : 'lidar-chip-inactive'
                      }`}
                    title={opt.desc}
                  >
                    {opt.icon} {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={() => refreshLayers()}
              className="lidar-btn lidar-btn-secondary w-full flex items-center justify-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Actualizar capas
            </button>
          </div>
        )}

        {/* Source Options (when no active layer) */}
        {!activeTilesetUrl && !isProcessing && (
          <div className="space-y-4">
            {/* Coverage Badge */}
            {hasCoverage !== null && (
              <div className={`lidar-coverage-badge ${hasCoverage ? 'lidar-coverage-available' : 'lidar-coverage-unavailable'
                }`}>
                {hasCoverage ? (
                  <>
                    <CheckCircle className="w-3.5 h-3.5" />
                    Cobertura PNOA disponible
                  </>
                ) : (
                  <>
                    <Cloud className="w-3.5 h-3.5" />
                    Sin cobertura PNOA
                  </>
                )}
              </div>
            )}

            {/* Download from PNOA */}
            <button
              onClick={handleStartProcessing}
              disabled={isProcessing || !hasCoverage}
              className="lidar-btn lidar-btn-primary w-full flex items-center justify-center gap-2"
            >
              <Database className="w-4 h-4" />
              <span>{hasCoverage ? 'Descargar de PNOA' : 'Sin cobertura'}</span>
            </button>

            {/* Divider */}
            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-slate-200 to-transparent" />
              <span className="text-xs text-slate-400 font-medium">o</span>
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-slate-200 to-transparent" />
            </div>

            {/* File Upload Dropzone */}
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              className={`lidar-dropzone cursor-pointer ${isDragOver ? 'lidar-dropzone-active' : ''}`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".laz,.las"
                onChange={handleFileInputChange}
                className="hidden"
              />
              <div className="flex flex-col items-center gap-2">
                {isUploading ? (
                  <Loader2 className="w-8 h-8 text-violet-500 animate-spin" />
                ) : (
                  <Upload className="w-8 h-8 text-violet-400" />
                )}
                <div className="text-center">
                  <p className="text-sm font-medium text-slate-700">
                    {isUploading ? 'Subiendo...' : 'Subir archivo .LAZ'}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    Dron LiDAR con georreferenciación
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Layers List */}
        {layers.length > 0 && (
          <div className="pt-4 border-t border-slate-100">
            <h4 className="lidar-label mb-3 flex items-center gap-1">
              <Layers className="w-3 h-3" />
              Capas Disponibles
            </h4>
            <div className="space-y-2 max-h-32 overflow-y-auto lidar-scrollbar">
              {layers.map((layer) => (
                <div
                  key={layer.id}
                  className="lidar-layer-item text-xs"
                >
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-violet-500" />
                    <span className="text-slate-700 font-medium truncate">
                      {layer.source}
                    </span>
                  </div>
                  <span className="text-slate-400">
                    {layer.point_count ? `${(layer.point_count / 1000000).toFixed(1)}M` : ''}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default LidarLayerControl;

