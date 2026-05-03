/**
 * LIDAR Config - Context panel component for tree details
 *
 * Shows when a parcel is selected and displays configuration
 * and tree information when trees are detected.
 */

import React from 'react';
import { Layers } from 'lucide-react';
import { SlotShell } from '@nekazari/viewer-kit';
import { Stack, FormGrid, FormField } from '@nekazari/ui-kit';
import { useTranslation } from '../../sdk';
import { useLidarContext } from '../../services/lidarContext';
import TreeInfo from './TreeInfo';
import type { TreeData } from '../../types';

const lidarAccent = { base: '#8B5CF6', soft: '#EDE9FE', strong: '#6D28D9' };

interface LidarConfigProps {
  selectedTree?: TreeData | null;
}

const LidarConfig: React.FC<LidarConfigProps> = ({ selectedTree }) => {
  const { t } = useTranslation('lidar');
  const {
    selectedEntityId,
    activeTilesetUrl,
    processingJob,
    colorMode
  } = useLidarContext();

  if (!selectedEntityId) {
    return null;
  }

  // If a tree is selected, show tree details
  if (selectedTree) {
    return <TreeInfo tree={selectedTree} />;
  }

  return (
    <SlotShell
      title={t('config.title')}
      icon={<Layers className="w-4 h-4" />}
      accent={lidarAccent}
    >
      <Stack gap="stack">
        <FormGrid columns={1}>
          {/* Parcel Info */}
          <FormField label={t('config.parcel')}>
            <p className="text-nkz-sm text-nkz-text-primary font-mono truncate">
              {selectedEntityId.split(':').pop()}
            </p>
          </FormField>

          {/* Layer Status */}
          {activeTilesetUrl && (
            <FormField label={t('config.activeLayer')}>
              <div className="flex items-center gap-nkz-inline">
                <div className="w-2 h-2 rounded-full bg-nkz-success" />
                <span className="text-nkz-sm text-nkz-success-strong">{t('config.pointCloudLoaded')}</span>
              </div>
            </FormField>
          )}

          {/* Color Mode */}
          {activeTilesetUrl && (
            <FormField label={t('config.viewMode')}>
              <p className="text-nkz-sm text-nkz-text-primary capitalize">
                {colorMode === 'ndvi' ? t('config.viewMode.ndvi') :
                  colorMode === 'height' ? t('config.viewMode.height') :
                    colorMode === 'rgb' ? t('config.viewMode.rgb') :
                      colorMode === 'classification' ? t('config.viewMode.classification') : colorMode}
              </p>
            </FormField>
          )}

          {/* Processing Status */}
          {processingJob && processingJob.status !== 'completed' && (
            <FormField label={t('config.processingStatus')}>
              <p className="text-nkz-sm text-nkz-text-primary">
                {processingJob.status_message || processingJob.status}
              </p>
              {processingJob.tree_count !== undefined && processingJob.tree_count > 0 && (
                <p className="text-nkz-xs text-nkz-success-strong mt-nkz-tight">
                  {t('config.treesDetected', { count: processingJob.tree_count })}
                </p>
              )}
            </FormField>
          )}

          {/* Results Summary */}
          {processingJob?.status === 'completed' && processingJob.tree_count !== undefined && (
            <div className="border-t border-nkz-border pt-nkz-stack">
              <FormField label={t('config.results')}>
                <div className="space-y-nkz-tight">
                  <p className="text-nkz-sm text-nkz-text-primary">
                    <strong>{t('config.treesDetected', { count: processingJob.tree_count })}</strong>
                  </p>
                  {processingJob.point_count && (
                    <p className="text-nkz-sm text-nkz-text-primary">
                      <strong>{t('config.points', { count: (processingJob.point_count / 1000000).toFixed(2) })}</strong>
                    </p>
                  )}
                </div>
                <p className="text-nkz-xs text-nkz-text-muted mt-nkz-tight">
                  {t('config.clickTree')}
                </p>
              </FormField>
            </div>
          )}
        </FormGrid>
      </Stack>
    </SlotShell>
  );
};

export { LidarConfig };
export default LidarConfig;
