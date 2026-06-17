/**
 * LiDAR Layer Toggle - Unified layer row for the Capas dropdown.
 *
 * Built on LayerMenuRow from @nekazari/module-kit.
 * Scope 'selected' mounts only the active tileset; 'all' mounts every layer.
 * Opacity slider intentionally omitted — Cesium3DTileset does not support
 * per-layer alpha the same way ImageryLayer does.
 */

import React from 'react';
import { LayerMenuRow } from '@nekazari/module-kit';
import { Mountain } from 'lucide-react';
import { useLidarContext, ColorMode } from '../../services/lidarContext';
import { useTranslation } from '../../sdk';

const COLOR_MODES: { value: ColorMode; icon: string }[] = [
  { value: 'height', icon: '\u{1F4CF}' },
  { value: 'ndvi', icon: '\u{1F33F}' },
  { value: 'rgb', icon: '\u{1F3A8}' },
  { value: 'classification', icon: '\u{1F3F7}' },
];

const LidarLayerToggle: React.FC = () => {
  const { t } = useTranslation('lidar');
  const {
    layers,
    activeTilesetUrl,
    setActiveTilesetUrl,
    selectedLayerId,
    setSelectedLayerId,
    layerScope,
    setLayerScope,
    layerVisible,
    setLayerVisible,
    colorMode,
    setColorMode,
    isProcessing,
  } = useLidarContext();

  const hasAnyLayer = Array.isArray(layers) && layers.length > 0;

  const handleToggle = (next: boolean) => {
    setLayerVisible(next);
    // When turning on under 'selected' scope, prime an active tileset
    // so the layer effect has something to mount.
    if (next && layerScope === 'selected' && !activeTilesetUrl && hasAnyLayer) {
      const pick = selectedLayerId
        ? layers.find((l: any) => l.id === selectedLayerId) || layers[0]
        : layers[0];
      if (pick?.tileset_url) {
        setActiveTilesetUrl(pick.tileset_url);
        setSelectedLayerId(pick.id);
      }
    }
  };

  const disabledReason =
    isProcessing ? (t('processing') || 'Procesando…')
    : !hasAnyLayer ? (t('noLayers') || 'Sin tilesets')
    : undefined;

  return (
    <LayerMenuRow
      moduleId="lidar"
      icon={<Mountain className="w-4 h-4" />}
      title="LiDAR"
      enabled={layerVisible}
      onToggle={handleToggle}
      scope={layerScope}
      onScopeChange={setLayerScope}
      disabledReason={disabledReason}
      scopeLabel={t('layerToggle.scope') || 'Ámbito'}
      selectedLabel={t('layerToggle.selected') || 'Seleccionada'}
      allLabel={t('layerToggle.all') || 'Todas'}
      mode={
        <div className="flex flex-wrap gap-nkz-tight">
          {COLOR_MODES.map(m => (
            <button
              key={m.value}
              type="button"
              aria-pressed={colorMode === m.value}
              onClick={() => setColorMode(m.value)}
              className={`px-nkz-inline py-nkz-tight text-nkz-xs rounded-nkz-md transition-colors ${
                colorMode === m.value
                  ? 'bg-nkz-accent-soft text-nkz-accent-strong'
                  : 'bg-nkz-surface-sunken text-nkz-text-muted hover:bg-nkz-surface'
              }`}
              title={t(`color.${m.value}`)}
            >
              {m.icon}
            </button>
          ))}
        </div>
      }
    />
  );
};

export default LidarLayerToggle;
