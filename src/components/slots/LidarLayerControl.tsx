/**
 * LIDAR Layer Control - Premium Control Panel
 *
 * Features:
 * - Check PNOA coverage with visual feedback
 * - Download from PNOA or upload custom .LAZ file
 * - Configure processing options (colorization, tree detection)
 * - Job progress monitoring with animations
 * - Layer management with delete confirmation
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Layers,
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
  Database,
  Trash2,
} from 'lucide-react';
import { useTranslation } from '../../sdk';
import { useLidarContext, ColorMode } from '../../services/lidarContext';
import { lidarApi } from '../../services/api';
import type { LazHeaderParseResult } from '../../workers/lazHeaderWorker';
import LazWorker from '../../workers/lazHeaderWorker?worker&inline';

const LEGENDS: Record<string, Array<{ color: string; label: string }>> = {
  height: [
    { color: '#0000ff', label: '0m' },
    { color: '#00ff00', label: '25m' },
    { color: '#ff0000', label: '50m+' },
  ],
  classification: [
    { color: '#8B5E3C', label: 'Suelo' },
    { color: '#00B31A', label: 'Vegetación' },
    { color: '#B3B3B3', label: 'Edificio' },
  ],
  heightAboveGround: [
    { color: '#8B5E3C', label: '0m' },
    { color: '#FFFF00', label: '1m' },
    { color: '#00FF00', label: '3m' },
    { color: '#FF0000', label: '5m+' },
  ],
  canopyCover: [
    { color: '#33CC33', label: 'Cubierta' },
    { color: '#006B00', label: 'Copa' },
    { color: '#8B5E3C', label: 'Suelo' },
  ],
  verticalDensity: [
    { color: '#0000ff', label: 'Baja' },
    { color: '#ffff00', label: 'Media' },
    { color: '#ff0000', label: 'Alta' },
  ],
  rgb: [],
};

const LidarLayerControl: React.FC = () => {
  const { t } = useTranslation('lidar');
  const context = useLidarContext();
  
  // FAILSAFE: Local state to mirror context if it's stuck or non-reactive
  const [localEntityId, setLocalEntityId] = useState<string | null>(context.selectedEntityId);

  useEffect(() => {
    // Listen for the global event we added to the Core dispatcher
    const handleGlobalSelect = (e: any) => {
      console.log('[LidarUI] Global event received:', e.detail.id);
      setLocalEntityId(e.detail.id);
    };
    window.addEventListener('nekazari:entity:selected' as any, handleGlobalSelect);
    
    // Initial check from URL if current context is empty (deep links)
    if (!localEntityId) {
      const params = new URLSearchParams(window.location.search);
      const entityId = params.get('entityId');
      if (entityId) setLocalEntityId(entityId);
    }

    return () => window.removeEventListener('nekazari:entity:selected' as any, handleGlobalSelect);
  }, []);

  // Use local ID as override for the UI logic
  const selectedEntityId = localEntityId || context.selectedEntityId;

  const {
    selectedEntityGeometry,
    isLoadingMetadata,
    activeTilesetUrl,
    colorMode,
    setColorMode,
    heightOffset,
    setHeightOffset,
    isProcessing,
    processingJob,
    processingConfig,
    setProcessingConfig,
    startProcessing,
    cancelProcessing,
    hasCoverage,
    checkCoverage,
    layers,
    refreshLayers,
    deleteLayer,
  } = context;

  const [showSettings, setShowSettings] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [deletingLayerId, setDeletingLayerId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [manualCrs, setManualCrs] = useState('');
  const [requiresManualCrs, setRequiresManualCrs] = useState(false);
  const [uploadJobStatus, setUploadJobStatus] = useState<{ progress: number; message: string } | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ id: string; filename: string; size_bytes: number }>>([]);
  const [deletingUploadId, setDeletingUploadId] = useState<string | null>(null);
  const [classificationMode, setClassificationMode] = useState<'native' | 'auto' | 'detect'>('detect');
  const [hasRgb, setHasRgb] = useState(true);
  const [showUploadOptions, setShowUploadOptions] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  const COLOR_MODE_OPTIONS: { value: ColorMode; label: string; icon: string; desc: string }[] = [
    { value: 'height', label: t('color.height'), icon: '\u{1F4CF}', desc: t('color.height.desc') },
    { value: 'classification', label: t('color.classification'), icon: '\u{1F3F7}\uFE0F', desc: t('color.classification.desc') },
    { value: 'heightAboveGround', label: t('color.hag'), icon: '\u{1F4D0}', desc: t('color.hag.desc') },
    { value: 'canopyCover', label: t('color.canopy'), icon: '\u{1F33F}', desc: t('color.canopy.desc') },
    { value: 'verticalDensity', label: t('color.density'), icon: '\u{1F4CA}', desc: t('color.density.desc') },
    { value: 'rgb', label: t('color.rgb'), icon: '\u{1F3A8}', desc: t('color.rgb.desc') },
  ];

  // Auto-dismiss errors after 8 seconds
  const setErrorWithTimeout = useCallback((error: string | null) => {
    if (errorTimeoutRef.current) clearTimeout(errorTimeoutRef.current);
    setUploadError(error);
    if (error) {
      errorTimeoutRef.current = setTimeout(() => setUploadError(null), 8000);
    }
  }, []);

  useEffect(() => {
    return () => {
      if (errorTimeoutRef.current) clearTimeout(errorTimeoutRef.current);
    };
  }, []);

  // Check coverage when entity is selected AND geometry is available
  useEffect(() => {
    if (selectedEntityGeometry && hasCoverage === null) {
      checkCoverage();
    }
  }, [selectedEntityGeometry, hasCoverage, checkCoverage]);

  // Fetch uploaded files list on mount
  const fetchUploads = useCallback(async () => {
    try {
      const result = await lidarApi.listUploads();
      setUploadedFiles(result.uploads);
    } catch {
      // silently fail — uploads list is non-critical
    }
  }, []);

  useEffect(() => { fetchUploads(); }, [fetchUploads]);

  const handleDeleteUpload = async (uploadId: string) => {
    setDeletingUploadId(uploadId);
    try {
      await lidarApi.deleteUpload(uploadId);
      setUploadedFiles(prev => prev.filter(f => f.id !== uploadId));
    } catch {
      // silently fail
    } finally {
      setDeletingUploadId(null);
    }
  };

  // =========================================================================
  // Handlers
  // =========================================================================

  const handleStartProcessing = async () => {
    if (!selectedEntityGeometry) {
      setErrorWithTimeout(t('errorNoGeometry'));
      return;
    }
    try {
      setErrorWithTimeout(null);
      await startProcessing();
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : t('errorProcessing');
      setErrorWithTimeout(msg);
    }
  };

  const handleFileUpload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.laz') && !file.name.toLowerCase().endsWith('.las')) {
      setErrorWithTimeout(t('errorFileType'));
      return;
    }

    const maxSize = 500 * 1024 * 1024;
    if (file.size > maxSize) {
      setErrorWithTimeout(t('errorFileSize'));
      return;
    }

    setErrorWithTimeout(null);

    try {
      // Parse LAZ header for CRS
      const parserWorker = new LazWorker();
      const headerInfo: LazHeaderParseResult = await new Promise((resolve, reject) => {
        parserWorker.onmessage = (ev) => resolve(ev.data as LazHeaderParseResult);
        parserWorker.onerror = (err) => reject(err);
        parserWorker.postMessage({ file });
        setTimeout(() => reject(new Error('Worker timeout')), 5000);
      });
      parserWorker.terminate();

      if (!headerInfo.hasProjectionVlr && !manualCrs.trim()) {
        setRequiresManualCrs(true);
        throw new Error(t('errorMissingCrs'));
      }

      // Store file and show classification options modal
      setPendingFile(file);
      setShowUploadOptions(true);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : t('errorUpload');
      setErrorWithTimeout(msg);
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

  const handleDeleteLayer = async (layerId: string) => {
    setDeletingLayerId(layerId);
    try {
      await deleteLayer(layerId);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Delete failed';
      setErrorWithTimeout(msg);
    } finally {
      setDeletingLayerId(null);
      setConfirmDeleteId(null);
    }
  };

  const doUpload = async () => {
    if (!pendingFile) return;
    const file = pendingFile;
    setShowUploadOptions(false);
    setPendingFile(null);
    setIsUploading(true);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('parcel_id', selectedEntityId || 'unknown');
      if (selectedEntityGeometry) formData.append('geometry_wkt', selectedEntityGeometry);
      formData.append('config', JSON.stringify(processingConfig));
      formData.append('classification_mode', classificationMode);
      if (hasRgb) formData.append('has_rgb', 'true');
      if (manualCrs.trim()) formData.append('source_crs', manualCrs.trim());

      const uploadResponse = await lidarApi.uploadFile(formData);
      const finalStatus = await lidarApi.pollJobStatus(
        uploadResponse.job_id,
        (status) => setUploadJobStatus({ progress: status.progress, message: status.status_message || '' }),
        2000, 300,
      );
      if (finalStatus.tileset_url) await refreshLayers();
      setUploadJobStatus(null);
      setRequiresManualCrs(false);
      setManualCrs('');
    } catch (error: unknown) {
      setUploadJobStatus(null);
      const msg = error instanceof Error ? error.message : t('errorUpload');
      setErrorWithTimeout(msg);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // =========================================================================
  // Render: Main Control Panel
  // =========================================================================

  if (!selectedEntityId) {
    return (
      <div className="lidar-module p-6 bg-white/80 backdrop-blur-sm rounded-xl border border-dashed border-slate-300 flex flex-col items-center justify-center gap-3 text-center min-h-[160px]">
        <div className="p-3 rounded-full bg-violet-50">
          <Layers className="w-8 h-8 text-violet-400" />
        </div>
        <div>
          <p className="text-sm font-semibold text-slate-700">{t('noParcelSelected')}</p>
          <p className="text-xs text-slate-500 mt-1">{t('selectParcelToUpload')}</p>
        </div>
      </div>
    );
  }

  if (isLoadingMetadata) {
    return (
      <div className="lidar-module p-4 bg-white/80 backdrop-blur-sm rounded-xl border border-slate-200/60 flex flex-col items-center justify-center gap-3 min-h-[200px]">
        <Loader2 className="w-8 h-8 text-violet-500 animate-spin" />
        <p className="text-sm text-slate-500 font-medium">{t('loadingMetadata')}</p>
      </div>
    );
  }

  return (
    <div className="lidar-module" style={{ marginBottom: '12px' }}>
    <div className="bg-white/80 backdrop-blur-sm rounded-xl border border-slate-200/60 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-100 bg-gradient-to-r from-violet-50/60 to-cyan-50/60">
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
            title={t('settings')}
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Settings Panel */}
        {showSettings && (
          <div className="p-4 bg-slate-50 rounded-xl space-y-4 border border-slate-200 lidar-slide-in">
            <h4 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-violet-500" />
              {t('processingOptions')}
            </h4>
            <p className="text-xs text-slate-500 -mt-2">{t('processingOptionsHint')}</p>

            {/* Color Mode */}
            <div>
              <label className="lidar-label flex items-center gap-1 mb-2">
                <Palette className="w-3 h-3" />
                {t('colorization')}
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
                <span className="text-sm text-slate-700">{t('detectTrees')}</span>
              </div>
            </label>

            {/* Tree Detection Options */}
            {processingConfig.detect_trees && (
              <div className="ml-4 pl-4 border-l-2 border-emerald-200 space-y-3 lidar-slide-in">
                <div>
                  <label className="text-xs text-slate-500 block mb-1">{t('minHeight')}</label>
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
                  <label className="text-xs text-slate-500 block mb-1">{t('searchRadius')}</label>
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
                {t('processing')}
              </span>
            </div>
            <div className="lidar-progress mb-2">
              <div
                className="lidar-progress-bar"
                style={{ width: `${processingJob.progress}%` }}
              />
            </div>
            <p className="text-xs text-violet-700">
              {processingJob.status_message || t('processingPointCloud')}
            </p>
            <button
              onClick={() => cancelProcessing()}
              className="mt-2 w-full text-xs px-3 py-1.5 rounded-lg bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 transition-colors"
            >
              {t('cancelProcessing')}
            </button>
          </div>
        )}

        {/* Upload Processing Status */}
        {isUploading && uploadJobStatus && (
          <div className="p-4 rounded-xl bg-gradient-to-br from-violet-50 to-cyan-50 border border-violet-200 lidar-pulse lidar-slide-in">
            <div className="flex items-center gap-2 mb-3">
              <Loader2 className="w-5 h-5 text-violet-600 animate-spin" />
              <span className="text-sm font-semibold text-violet-900">
                {t('processing')}
              </span>
            </div>
            <div className="lidar-progress mb-2">
              <div
                className="lidar-progress-bar"
                style={{ width: `${uploadJobStatus.progress}%` }}
              />
            </div>
            <p className="text-xs text-violet-700">
              {uploadJobStatus.message || t('processingPointCloud')}
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
                <span className="text-sm font-semibold text-emerald-900">{t('activeLayer')}</span>
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

              {LEGENDS[colorMode] && LEGENDS[colorMode].length > 0 && (
                <div className="flex gap-2 mt-2 text-[10px] text-slate-500">
                  {LEGENDS[colorMode].map((item, i) => (
                    <span key={i} className="flex items-center gap-1">
                      <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: item.color }} />
                      {item.label}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Height offset slider */}
            <div className="mt-3 pt-3 border-t border-slate-100">
              <label className="text-xs text-slate-500 flex items-center justify-between">
                <span>{t('heightOffset')}: {heightOffset > 0 ? '+' : ''}{heightOffset}m</span>
              </label>
              <input
                type="range"
                min={-100}
                max={20}
                step={1}
                value={heightOffset}
                onChange={(e) => setHeightOffset(parseInt(e.target.value))}
                className="w-full h-1.5 mt-1 accent-violet-500"
              />
              <div className="flex justify-between text-[10px] text-slate-400">
                <span>-100m</span><span>0m</span><span>+20m</span>
              </div>
            </div>

            <button
              onClick={() => refreshLayers()}
              className="lidar-btn lidar-btn-secondary w-full flex items-center justify-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              {t('refreshLayers')}
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
                    {t('coverageAvailable')}
                  </>
                ) : (
                  <>
                    <Cloud className="w-3.5 h-3.5" />
                    {t('noCoverage')}
                  </>
                )}
              </div>
            )}

            {/* Download from PNOA */}
            <button
              onClick={handleStartProcessing}
              disabled={isProcessing || !hasCoverage}
              className="lidar-btn lidar-btn-primary w-full flex items-center justify-center gap-2"
              style={{ background: 'linear-gradient(135deg, #8b5cf6 0%, #06b6d4 100%)' }}
            >
              <Database className="w-4 h-4" />
              <span>{hasCoverage ? t('downloadPnoa') : t('noCoverage')}</span>
            </button>

            {/* Divider */}
            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-slate-200 to-transparent" />
              <span className="text-xs text-slate-400 font-medium">{t('or')}</span>
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-slate-200 to-transparent" />
            </div>

            {/* File Upload Dropzone */}
            {requiresManualCrs && (
              <div className="p-3 rounded-lg border border-amber-300 bg-amber-50">
                <label className="text-xs text-amber-800 block mb-1">{t('manualCrsLabel')}</label>
                <input
                  value={manualCrs}
                  onChange={(e) => setManualCrs(e.target.value)}
                  placeholder="EPSG:25830+5782"
                  className="w-full border border-amber-300 rounded px-2 py-1 text-sm"
                />
              </div>
            )}
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
                    {isUploading ? t('uploading') : t('uploadLaz')}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    {t('droneLidar')}
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
              {t('availableLayers')}
            </h4>
            <div className="space-y-2 max-h-40 overflow-y-auto lidar-scrollbar">
              {layers.map((layer) => (
                <div key={layer.id}>
                  <div className="lidar-layer-item text-xs">
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <div className="w-1.5 h-1.5 rounded-full bg-violet-500 flex-shrink-0" />
                      <span className="text-slate-700 font-medium truncate">
                        {layer.source}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400">
                        {layer.point_count ? `${(layer.point_count / 1000000).toFixed(1)}M` : ''}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmDeleteId(confirmDeleteId === layer.id ? null : layer.id);
                        }}
                        className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors"
                        title={t('deleteLayer')}
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                  {/* Delete confirmation */}
                  {confirmDeleteId === layer.id && (
                    <div className="mt-1 p-2 bg-red-50 rounded-lg border border-red-200 lidar-slide-in">
                      <p className="text-xs text-red-700 mb-2">{t('deleteConfirm')}</p>
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleDeleteLayer(layer.id)}
                          disabled={deletingLayerId === layer.id}
                          className="flex-1 text-xs px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                        >
                          {deletingLayerId === layer.id ? t('deleting') : t('deleteLayer')}
                        </button>
                        <button
                          onClick={() => setConfirmDeleteId(null)}
                          className="flex-1 text-xs px-2 py-1 bg-white text-slate-700 rounded border border-slate-200 hover:bg-slate-50"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Uploaded Files */}
        {uploadedFiles.length > 0 && (
          <div className="pt-4 border-t border-slate-100">
            <h4 className="lidar-label mb-3 flex items-center gap-1">
              <Upload className="w-3 h-3" />
              {t('uploadedFiles')}
            </h4>
            <div className="space-y-1 max-h-32 overflow-y-auto lidar-scrollbar">
              {uploadedFiles.map((f) => (
                <div key={f.id} className="flex items-center justify-between text-xs py-1 px-2 rounded hover:bg-slate-50">
                  <span className="text-slate-600 truncate flex-1">{f.filename}</span>
                  <span className="text-slate-400 mx-2">{(f.size_bytes / 1048576).toFixed(1)} MB</span>
                  <button
                    onClick={() => handleDeleteUpload(f.id)}
                    disabled={deletingUploadId === f.id}
                    className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors"
                    title={t('deleteLayer')}
                  >
                    {deletingUploadId === f.id ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Trash2 className="w-3 h-3" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Upload Classification Modal */}
        {showUploadOptions && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => { setShowUploadOptions(false); setPendingFile(null); }}>
            <div className="bg-white rounded-xl p-5 shadow-xl max-w-sm w-full mx-4" onClick={(e) => e.stopPropagation()}>
              <h3 className="font-semibold text-slate-800 mb-3">{t('uploadClassification')}</h3>

              <label className="flex items-center gap-2 mb-2 text-sm cursor-pointer">
                <input type="radio" name="classMode" value="native" checked={classificationMode === 'native'}
                  onChange={() => setClassificationMode('native')} />
                {t('classificationNative')}
              </label>
              <label className="flex items-center gap-2 mb-2 text-sm cursor-pointer">
                <input type="radio" name="classMode" value="auto" checked={classificationMode === 'auto'}
                  onChange={() => setClassificationMode('auto')} />
                {t('classificationAuto')}
              </label>
              <label className="flex items-center gap-2 mb-4 text-sm cursor-pointer">
                <input type="radio" name="classMode" value="detect" checked={classificationMode === 'detect'}
                  onChange={() => setClassificationMode('detect')} />
                {t('classificationDetect')}
              </label>

              <label className="flex items-center gap-2 mb-4 text-sm cursor-pointer">
                <input type="checkbox" checked={hasRgb} onChange={(e) => setHasRgb(e.target.checked)} />
                {t('hasRgb')}
              </label>

              <div className="flex gap-2">
                <button onClick={doUpload} className="flex-1 px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium">
                  {t('continue')}
                </button>
                <button onClick={() => { setShowUploadOptions(false); setPendingFile(null); }}
                  className="flex-1 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg text-sm">
                  {t('cancel')}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
    </div>
  );
};

export default LidarLayerControl;
