/**
 * LiDAR Layer Toggle - Lightweight toggle for the layer dropdown.
 *
 * Shows a simple on/off indicator and color mode selector.
 * The full control panel lives in the context-panel (right sidebar).
 */

import React from 'react';
import { SlotShellCompact } from '@nekazari/viewer-kit';
import { Toggle } from '@nekazari/ui-kit';
import { useTranslation } from '../../sdk';
import { useLidarContext, ColorMode } from '../../services/lidarContext';

const lidarAccent = { base: '#8B5CF6', soft: '#EDE9FE', strong: '#6D28D9' };

const COLOR_MODES: { value: ColorMode; icon: string }[] = [
  { value: 'height', icon: '\u{1F4CF}' },
  { value: 'ndvi', icon: '\u{1F33F}' },
  { value: 'rgb', icon: '\u{1F3A8}' },
  { value: 'classification', icon: '\u{1F3F7}️' },
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
    <SlotShellCompact moduleId="lidar" accent={lidarAccent}>
      <div className="flex flex-col gap-nkz-tight">
        <Toggle
          checked={isActive}
          onChange={handleToggle}
          label="LiDAR"
          disabled={!layers || layers.length === 0 || isProcessing}
        />

        {/* Color mode pills (only when layer is active) */}
        {isActive && (
          <div className="flex justify-end gap-nkz-tight">
            {COLOR_MODES.map((m) => (
              <button
                key={m.value}
                onClick={(e) => {
                  e.stopPropagation();
                  setColorMode(m.value);
                }}
                className={`px-nkz-inline py-nkz-tight rounded-nkz-md text-nkz-xs transition-colors ${
                  colorMode === m.value
                    ? 'bg-nkz-accent-soft text-nkz-accent-strong'
                    : 'bg-nkz-surface-sunken hover:bg-nkz-surface text-nkz-text-muted'
                }`}
                title={t(`color.${m.value}`)}
              >
                {m.icon}
              </button>
            ))}
          </div>
        )}
      </div>
    </SlotShellCompact>
  );
};

export default LidarLayerToggle;
