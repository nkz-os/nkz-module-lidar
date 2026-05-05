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
  TreeDeciduous,
  Palette,
  Sparkles,
  Cloud,
  Database,
  Trash2,
} from 'lucide-react';
import { SlotShell } from '@nekazari/viewer-kit';
import {
  Stack,
  Toggle,
  Select,
  Slider,
  Button,
  Badge,
  Spinner,
  ProgressBar,
  Input,
  IconButton,
  EmptyState,
} from '@nekazari/ui-kit';
import { useTranslation } from '../../sdk';
import { useLidarContext, ColorMode } from '../../services/lidarContext';
import { lidarApi } from '../../services/api';
import type { LazHeaderParseResult } from '../../workers/lazHeaderWorker';
import LazWorker from '../../workers/lazHeaderWorker?worker&inline';

const lidarAccent = { base: '#8B5CF6', soft: '#EDE9FE', strong: '#6D28D9' };

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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  const COLOR_MODE_OPTIONS: { value: ColorMode; label: string; icon: string; desc: string }[] = [
    { value: 'height', label: t('color.height'), icon: '\u{1F4CF}', desc: t('color.height.desc') },
    { value: 'ndvi', label: t('color.ndvi'), icon: '\u{1F33F}', desc: t('color.ndvi.desc') },
    { value: 'rgb', label: t('color.rgb'), icon: '\u{1F3A8}', desc: t('color.rgb.desc') },
    { value: 'classification', label: t('color.classification'), icon: '\u{1F3F7}️', desc: t('color.classification.desc') },
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

    setIsUploading(true);
    setErrorWithTimeout(null);

    try {
      // Lazy load worker or handle potential failure
      const parserWorker = new LazWorker();
      const headerInfo: LazHeaderParseResult = await new Promise((resolve, reject) => {
        parserWorker.onmessage = (ev) => resolve(ev.data as LazHeaderParseResult);
        parserWorker.onerror = (err) => reject(err);
        parserWorker.postMessage({ file });
        // Fail-safe timeout for worker
        setTimeout(() => reject(new Error('Worker timeout')), 5000);
      });
      parserWorker.terminate();

      if (!headerInfo.hasProjectionVlr && !manualCrs.trim()) {
        setRequiresManualCrs(true);
        throw new Error(t('errorMissingCrs'));
      }

      const formData = new FormData();
      formData.append('file', file);
      formData.append('parcel_id', selectedEntityId || 'unknown');
      if (selectedEntityGeometry) {
        formData.append('geometry_wkt', selectedEntityGeometry);
      }
      formData.append('config', JSON.stringify(processingConfig));
      if (manualCrs.trim()) {
        formData.append('source_crs', manualCrs.trim());
      }

      const uploadResponse = await lidarApi.uploadFile(formData);

      // Poll until job completes (same flow as PNOA download)
      const finalStatus = await lidarApi.pollJobStatus(
        uploadResponse.job_id,
        (status) => {
          setUploadJobStatus({ progress: status.progress, message: status.status_message || '' });
        },
        2000,
        300,
      );

      if (finalStatus.tileset_url) {
        await refreshLayers();
      }
      setUploadJobStatus(null);
      setRequiresManualCrs(false);
      setManualCrs('');
    } catch (error: unknown) {
      setUploadJobStatus(null);
      const msg = error instanceof Error ? error.message : t('errorUpload');
      setErrorWithTimeout(msg);
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

  // =========================================================================
  // Render: Main Control Panel
  // =========================================================================

  if (!selectedEntityId) {
    return (
      <SlotShell moduleId="lidar" accent={lidarAccent}>
        <EmptyState
          icon={<Layers size={32} />}
          title={t('noParcelSelected')}
          description={t('selectParcelToUpload')}
        />
      </SlotShell>
    );
  }

  if (isLoadingMetadata) {
    return (
      <SlotShell moduleId="lidar" accent={lidarAccent}>
        <div className="flex flex-col items-center justify-center gap-nkz-stack py-nkz-section">
          <Spinner size="md" />
          <p className="text-nkz-sm text-nkz-text-muted font-medium">{t('loadingMetadata')}</p>
        </div>
      </SlotShell>
    );
  }

  return (
    <SlotShell
      title="Control LiDAR"
      icon={<Layers className="w-4 h-4" />}
      collapsible
      accent={lidarAccent}
    >
      <Stack gap="stack">
        {/* Settings Panel */}
        {showSettings && (
          <div className="bg-nkz-surface-sunken rounded-nkz-md p-nkz-stack">
            <Stack gap="stack">
              <h4 className="text-nkz-sm font-semibold text-nkz-text-primary flex items-center gap-nkz-inline">
                <Sparkles className="w-4 h-4 text-nkz-accent-base" />
                {t('processingOptions')}
              </h4>
              <p className="text-nkz-xs text-nkz-text-muted -mt-nkz-stack">{t('processingOptionsHint')}</p>

              {/* Color Mode */}
              <div>
                <label className="text-nkz-xs font-semibold uppercase tracking-wider text-nkz-text-muted flex items-center gap-nkz-tight mb-nkz-tight">
                  <Palette className="w-3 h-3" />
                  {t('colorization')}
                </label>
                <Select
                  value={processingConfig.colorize_by}
                  onChange={(v) => setProcessingConfig({
                    ...processingConfig,
                    colorize_by: v as ColorMode
                  })}
                  options={COLOR_MODE_OPTIONS.map(opt => ({
                    value: opt.value,
                    label: `${opt.icon} ${opt.label}`
                  }))}
                  size="sm"
                />
              </div>

              {/* Tree Detection Toggle */}
              <div className="bg-nkz-surface rounded-nkz-md p-nkz-inline border border-nkz-border">
                <Toggle
                  checked={processingConfig.detect_trees}
                  onChange={(v) => setProcessingConfig({
                    ...processingConfig,
                    detect_trees: v
                  })}
                  label={t('detectTrees')}
                />
              </div>

              {/* Tree Detection Options */}
              {processingConfig.detect_trees && (
                <div className="ml-nkz-inline pl-nkz-inline border-l-2 border-nkz-success space-y-nkz-stack">
                  <div>
                    <label className="text-nkz-xs text-nkz-text-muted block mb-nkz-tight">{t('minHeight')}</label>
                    <Input
                      type="number"
                      value={processingConfig.tree_min_height}
                      onChange={(e) => setProcessingConfig({
                        ...processingConfig,
                        tree_min_height: parseFloat(e.target.value) || 2.0
                      })}
                      size="sm"
                    />
                  </div>
                  <div>
                    <label className="text-nkz-xs text-nkz-text-muted block mb-nkz-tight">{t('searchRadius')}</label>
                    <Input
                      type="number"
                      value={processingConfig.tree_search_radius}
                      onChange={(e) => setProcessingConfig({
                        ...processingConfig,
                        tree_search_radius: parseFloat(e.target.value) || 3.0
                      })}
                      size="sm"
                    />
                  </div>
                </div>
              )}
            </Stack>
          </div>
        )}

        {/* Processing Status */}
        {isProcessing && processingJob && (
          <div className="bg-nkz-accent-soft rounded-nkz-md p-nkz-stack border border-nkz-accent-base">
            <Stack gap="inline">
              <div className="flex items-center gap-nkz-inline">
                <Spinner size="sm" />
                <span className="text-nkz-sm font-semibold text-nkz-accent-strong">
                  {t('processing')}
                </span>
              </div>
              <ProgressBar value={processingJob.progress} intent="default" />
              <p className="text-nkz-xs text-nkz-accent-strong">
                {processingJob.status_message || t('processingPointCloud')}
              </p>
              <Button
                variant="danger"
                size="sm"
                onClick={() => cancelProcessing()}
              >
                {t('cancelProcessing')}
              </Button>
            </Stack>
          </div>
        )}

        {/* Upload Processing Status */}
        {isUploading && uploadJobStatus && (
          <div className="bg-nkz-accent-soft rounded-nkz-md p-nkz-stack border border-nkz-accent-base">
            <Stack gap="inline">
              <div className="flex items-center gap-nkz-inline">
                <Spinner size="sm" />
                <span className="text-nkz-sm font-semibold text-nkz-accent-strong">
                  {t('processing')}
                </span>
              </div>
              <ProgressBar value={uploadJobStatus.progress} intent="default" />
              <p className="text-nkz-xs text-nkz-accent-strong">
                {uploadJobStatus.message || t('processingPointCloud')}
              </p>
            </Stack>
          </div>
        )}

        {/* Error Display */}
        {uploadError && (
          <Badge intent="negative" className="flex items-center gap-nkz-tight">
            <XCircle className="w-4 h-4 flex-shrink-0" />
            <span className="text-nkz-xs">{uploadError}</span>
          </Badge>
        )}

        {/* Active Layer */}
        {activeTilesetUrl && !isProcessing && (
          <div className="bg-nkz-success-soft rounded-nkz-md p-nkz-stack border border-nkz-success">
            <Stack gap="inline">
              <Badge intent="positive">{t('activeLayer')}</Badge>

              {/* Color Mode Pills */}
              <div className="flex flex-wrap gap-nkz-tight">
                {COLOR_MODE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setColorMode(opt.value)}
                    className={`px-nkz-inline py-nkz-tight text-nkz-xs font-medium rounded-nkz-full transition-colors ${
                      colorMode === opt.value
                        ? 'bg-nkz-accent-base text-nkz-text-on-accent'
                        : 'bg-nkz-surface-sunken text-nkz-text-secondary hover:bg-nkz-border'
                    }`}
                    title={opt.desc}
                  >
                    {opt.icon} {opt.label}
                  </button>
                ))}
              </div>

              {/* Height offset slider */}
              <Slider
                value={heightOffset}
                onChange={setHeightOffset}
                min={-100}
                max={20}
                step={1}
                label={t('heightOffset')}
                unit="m"
              />

              <Button
                variant="ghost"
                size="sm"
                onClick={() => refreshLayers()}
                leadingIcon={<RefreshCw className="w-4 h-4" />}
              >
                {t('refreshLayers')}
              </Button>
            </Stack>
          </div>
        )}

        {/* Source Options (when no active layer) */}
        {!activeTilesetUrl && !isProcessing && (
          <Stack gap="stack">
            {/* Coverage Badge */}
            {hasCoverage !== null && (
              <Badge intent={hasCoverage ? 'positive' : 'warning'}>
                {hasCoverage ? (
                  <span className="flex items-center gap-nkz-tight">
                    <CheckCircle className="w-3.5 h-3.5" />
                    {t('coverageAvailable')}
                  </span>
                ) : (
                  <span className="flex items-center gap-nkz-tight">
                    <Cloud className="w-3.5 h-3.5" />
                    {t('noCoverage')}
                  </span>
                )}
              </Badge>
            )}

            {/* Download from PNOA */}
            <Button
              variant="primary"
              size="md"
              onClick={handleStartProcessing}
              disabled={isProcessing || !hasCoverage}
              leadingIcon={<Database className="w-4 h-4" />}
            >
              {hasCoverage ? t('downloadPnoa') : t('noCoverage')}
            </Button>

            {/* Divider */}
            <div className="flex items-center gap-nkz-inline">
              <div className="flex-1 h-px bg-nkz-border" />
              <span className="text-nkz-xs text-nkz-text-muted font-medium">{t('or')}</span>
              <div className="flex-1 h-px bg-nkz-border" />
            </div>

            {/* File Upload Dropzone */}
            {requiresManualCrs && (
              <div className="bg-nkz-warning-soft rounded-nkz-md p-nkz-stack border border-nkz-warning">
                <Stack gap="tight">
                  <label className="text-nkz-xs text-nkz-warning-strong">{t('manualCrsLabel')}</label>
                  <Input
                    value={manualCrs}
                    onChange={(e) => setManualCrs(e.target.value)}
                    placeholder="EPSG:25830+5782"
                    size="sm"
                  />
                </Stack>
              </div>
            )}
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-nkz-lg p-nkz-section text-center cursor-pointer transition-colors ${
                isDragOver
                  ? 'border-nkz-accent-base bg-nkz-accent-soft'
                  : 'border-nkz-border hover:border-nkz-accent-base hover:bg-nkz-accent-soft'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".laz,.las"
                onChange={handleFileInputChange}
                className="hidden"
              />
              <div className="flex flex-col items-center gap-nkz-inline">
                {isUploading ? (
                  <Spinner size="md" />
                ) : (
                  <Upload className="w-8 h-8 text-nkz-accent-base" />
                )}
                <div className="text-center">
                  <p className="text-nkz-sm font-medium text-nkz-text-primary">
                    {isUploading ? t('uploading') : t('uploadLaz')}
                  </p>
                  <p className="text-nkz-xs text-nkz-text-muted mt-nkz-tight">
                    {t('droneLidar')}
                  </p>
                </div>
              </div>
            </div>
          </Stack>
        )}

        {/* Layers List */}
        {layers.length > 0 && (
          <div className="pt-nkz-stack border-t border-nkz-border">
            <Stack gap="inline">
              <h4 className="text-nkz-xs font-semibold uppercase tracking-wider text-nkz-text-muted flex items-center gap-nkz-tight">
                <Layers className="w-3 h-3" />
                {t('availableLayers')}
              </h4>
              <div className="flex flex-col gap-nkz-tight max-h-40 overflow-y-auto">
                {layers.map((layer) => (
                  <div key={layer.id}>
                    <div className="flex items-center justify-between p-nkz-inline rounded-nkz-md bg-nkz-surface-sunken hover:bg-nkz-surface transition-colors text-nkz-xs">
                      <div className="flex items-center gap-nkz-inline flex-1 min-w-0">
                        <div className="w-1.5 h-1.5 rounded-full bg-nkz-accent-base flex-shrink-0" />
                        <span className="text-nkz-sm text-nkz-text-primary font-medium truncate">
                          {layer.source}
                        </span>
                      </div>
                      <div className="flex items-center gap-nkz-inline">
                        <span className="text-nkz-xs text-nkz-text-muted">
                          {layer.point_count ? `${(layer.point_count / 1000000).toFixed(1)}M` : ''}
                        </span>
                        <IconButton
                          aria-label={t('deleteLayer')}
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmDeleteId(confirmDeleteId === layer.id ? null : layer.id);
                          }}
                        >
                          <Trash2 className="w-3 h-3" />
                        </IconButton>
                      </div>
                    </div>
                    {/* Delete confirmation */}
                    {confirmDeleteId === layer.id && (
                      <div className="mt-nkz-tight p-nkz-inline bg-nkz-danger-soft rounded-nkz-md border border-nkz-danger">
                        <Stack gap="inline">
                          <p className="text-nkz-xs text-nkz-danger-strong">{t('deleteConfirm')}</p>
                          <div className="flex gap-nkz-inline">
                            <Button
                              variant="danger"
                              size="sm"
                              onClick={() => handleDeleteLayer(layer.id)}
                              disabled={deletingLayerId === layer.id}
                            >
                              {deletingLayerId === layer.id ? t('deleting') : t('deleteLayer')}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setConfirmDeleteId(null)}
                            >
                              Cancel
                            </Button>
                          </div>
                        </Stack>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Stack>
          </div>
        )}

        {/* Uploaded Files */}
        {uploadedFiles.length > 0 && (
          <div className="pt-nkz-stack border-t border-nkz-border">
            <Stack gap="inline">
              <h4 className="text-nkz-xs font-semibold uppercase tracking-wider text-nkz-text-muted flex items-center gap-nkz-tight">
                <Upload className="w-3 h-3" />
                {t('uploadedFiles')}
              </h4>
              <div className="flex flex-col gap-nkz-tight max-h-32 overflow-y-auto">
                {uploadedFiles.map((f) => (
                  <div key={f.id} className="flex items-center justify-between text-nkz-xs py-nkz-tight px-nkz-inline rounded-nkz-md hover:bg-nkz-surface-sunken">
                    <span className="text-nkz-text-secondary truncate flex-1">{f.filename}</span>
                    <span className="text-nkz-text-muted mx-nkz-inline">{(f.size_bytes / 1048576).toFixed(1)} MB</span>
                    <IconButton
                      aria-label={t('deleteLayer')}
                      size="sm"
                      onClick={() => handleDeleteUpload(f.id)}
                      disabled={deletingUploadId === f.id}
                    >
                      {deletingUploadId === f.id ? (
                        <Spinner size="sm" />
                      ) : (
                        <Trash2 className="w-3 h-3" />
                      )}
                    </IconButton>
                  </div>
                ))}
              </div>
            </Stack>
          </div>
        )}
      </Stack>
    </SlotShell>
  );
};

export default LidarLayerControl;
