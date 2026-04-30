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
  { value: 'classification', icon: '\u{1F3F7}\uFE0F' },
  { value: 'heightAboveGround', icon: '\u{1F4D0}' },
  { value: 'canopyCover', icon: '\u{1F33F}' },
  { value: 'verticalDensity', icon: '\u{1F4CA}' },
  { value: 'rgb', icon: '\u{1F3A8}' },
];

const LidarLayerToggle: React.FC = () => {
  const { t } = useTranslation('lidar');
  const {
    selectedEntityId: _selectedEntityId,
    activeTilesetUrl,
    setActiveTilesetUrl,
    layers,
    selectedLayerId,
    setSelectedLayerId,
    colorMode,
    setColorMode,
    isProcessing,
    hasCoverage: _hasCoverage,
  } = useLidarContext();

  const handleToggle = () => {
    if (activeTilesetUrl) {
      // Turn off layer
      setActiveTilesetUrl(null);
      setSelectedLayerId(null);
    } else if (layers && layers.length > 0) {
      // Turn on the first available layer or the previously selected one
      const layerToActivate = selectedLayerId 
        ? layers.find(l => l.id === selectedLayerId) || layers[0]
        : layers[0];
      
      setActiveTilesetUrl(layerToActivate.tileset_url);
      setSelectedLayerId(layerToActivate.id);
    }
  };

  const isActive = !!activeTilesetUrl;

  return (
    <div className="space-y-1 mb-2">
      <button
        onClick={handleToggle}
        disabled={!layers || layers.length === 0 || isProcessing}
        className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-all ${
          isActive
            ? 'bg-blue-50 text-blue-700 border border-blue-200'
            : 'hover:bg-slate-50 text-slate-600'
        } ${(!layers || layers.length === 0) && !isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <span className={isActive ? 'text-violet-600' : 'text-slate-400'}>
          <Layers className="w-4 h-4" />
        </span>
        <span className="flex-1 text-left text-sm">LiDAR</span>
        
        {isProcessing ? (
          <Loader2 className="w-3.5 h-3.5 text-violet-500 animate-spin" />
        ) : (
          <div className={`w-3 h-3 rounded-full transition-colors ${
            isActive ? 'bg-blue-500' : 
            (layers && layers.length > 0 ? 'bg-slate-300' : 'bg-slate-200')
          }`} />
        )}
      </button>

      {/* Color mode pills (only when layer is active) */}
      {isActive && (
        <div className="flex justify-end gap-1 px-2">
          {COLOR_MODES.map((m) => (
            <button
              key={m.value}
              onClick={(e) => {
                e.stopPropagation();
                setColorMode(m.value);
              }}
              className={`px-1.5 py-0.5 rounded text-xs transition-colors ${
                colorMode === m.value
                  ? 'bg-violet-100 text-violet-700 border border-violet-200'
                  : 'bg-white hover:bg-slate-50 text-slate-500 border border-slate-200'
              }`}
              title={t(`color.${m.value}`)}
            >
              {m.icon}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default LidarLayerToggle;
