/**
 * LiDAR Layer Toggle - Lightweight toggle for the layer dropdown.
 *
 * Shows a simple on/off indicator and color mode selector.
 * The full control panel lives in the context-panel (right sidebar).
 */

import React from 'react';
import { Layers, Loader2 } from 'lucide-react';
import { useTranslation } from '../../sdk';
import { useLidarContext, ColorMode } from '../../services/lidarContext';

const COLOR_MODES: { value: ColorMode; icon: string }[] = [
  { value: 'height', icon: '\u{1F4CF}' },
  { value: 'ndvi', icon: '\u{1F33F}' },
  { value: 'rgb', icon: '\u{1F3A8}' },
  { value: 'classification', icon: '\u{1F3F7}\uFE0F' },
];

const LidarLayerToggle: React.FC = () => {
  const { t } = useTranslation('lidar');
  const {
    selectedEntityId,
    activeTilesetUrl,
    colorMode,
    setColorMode,
    isProcessing,
    hasCoverage,
  } = useLidarContext();

  if (!selectedEntityId) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 text-slate-400 text-sm">
        <Layers className="w-4 h-4" />
        <span>LiDAR</span>
      </div>
    );
  }

  return (
    <div className="px-3 py-2 space-y-2">
      {/* Status row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${
            activeTilesetUrl ? 'bg-emerald-500' :
            isProcessing ? 'bg-amber-500 animate-pulse' :
            hasCoverage ? 'bg-violet-500' : 'bg-slate-300'
          }`} />
          <span className="text-sm font-medium text-slate-700">LiDAR</span>
        </div>
        {isProcessing && <Loader2 className="w-3.5 h-3.5 text-violet-500 animate-spin" />}
      </div>

      {/* Color mode pills (only when layer is active) */}
      {activeTilesetUrl && (
        <div className="flex gap-1">
          {COLOR_MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => setColorMode(m.value)}
              className={`px-1.5 py-0.5 rounded text-xs transition-colors ${
                colorMode === m.value
                  ? 'bg-violet-100 text-violet-700'
                  : 'hover:bg-slate-100 text-slate-500'
              }`}
              title={t(`color.${m.value}`)}
            >
              {m.icon}
            </button>
          ))}
        </div>
      )}

      {/* Brief status text */}
      {!activeTilesetUrl && !isProcessing && (
        <p className="text-xs text-slate-400">
          {hasCoverage === null ? '' :
           hasCoverage ? t('coverageAvailable') : t('noCoverage')}
        </p>
      )}
    </div>
  );
};

export default LidarLayerToggle;
