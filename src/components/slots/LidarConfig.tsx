/**
 * LIDAR Config - Context panel component for tree details
 *
 * Shows when a parcel is selected and displays configuration
 * and tree information when trees are detected.
 */

import React from 'react';
import { useUIKit } from '../../hooks/useUIKit';
import { useTranslation } from '../../sdk';
import { useLidarContext } from '../../services/lidarContext';
import TreeInfo from './TreeInfo';
import type { TreeData } from '../../types';

interface LidarConfigProps {
  selectedTree?: TreeData | null;
}

const LidarConfig: React.FC<LidarConfigProps> = ({ selectedTree }) => {
  const { Card } = useUIKit();
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
    <div className="lidar-module" style={{ marginBottom: '12px' }}>
    <Card padding="md" className="bg-white/90 backdrop-blur-md border border-slate-200/50 rounded-xl">
      <div className="space-y-4">
        <h3 className="font-semibold text-slate-800">{t('config.title')}</h3>

        <div className="space-y-3">
          {/* Parcel Info */}
          <div>
            <label className="text-xs font-medium text-slate-600 uppercase tracking-wider">
              {t('config.parcel')}
            </label>
            <p className="text-sm text-slate-800 mt-1 font-mono truncate">
              {selectedEntityId.split(':').pop()}
            </p>
          </div>

          {/* Layer Status */}
          {activeTilesetUrl && (
            <div>
              <label className="text-xs font-medium text-slate-600 uppercase tracking-wider">
                {t('config.activeLayer')}
              </label>
              <div className="flex items-center gap-2 mt-1">
                <div className="w-2 h-2 rounded-full bg-green-500"></div>
                <span className="text-sm text-green-700">{t('config.pointCloudLoaded')}</span>
              </div>
            </div>
          )}

          {/* Color Mode */}
          {activeTilesetUrl && (
            <div>
              <label className="text-xs font-medium text-slate-600 uppercase tracking-wider">
                {t('config.viewMode')}
              </label>
              <p className="text-sm text-slate-800 mt-1 capitalize">
                {colorMode === 'height' ? t('config.viewMode.height') :
                  colorMode === 'classification' ? t('config.viewMode.classification') :
                    colorMode === 'heightAboveGround' ? t('config.viewMode.hag') :
                      colorMode === 'canopyCover' ? t('config.viewMode.canopy') :
                        colorMode === 'verticalDensity' ? t('config.viewMode.density') :
                          colorMode === 'rgb' ? t('config.viewMode.rgb') : colorMode}
              </p>
            </div>
          )}

          {/* Processing Status */}
          {processingJob && processingJob.status !== 'completed' && (
            <div>
              <label className="text-xs font-medium text-slate-600 uppercase tracking-wider">
                {t('config.processingStatus')}
              </label>
              <p className="text-sm text-slate-800 mt-1">
                {processingJob.status_message || processingJob.status}
              </p>
              {processingJob.tree_count !== undefined && processingJob.tree_count > 0 && (
                <p className="text-xs text-green-600 mt-1">
                  {t('config.treesDetected', { count: processingJob.tree_count })}
                </p>
              )}
            </div>
          )}

          {/* Results Summary */}
          {processingJob?.status === 'completed' && processingJob.tree_count !== undefined && (
            <div className="border-t border-slate-100 pt-3">
              <label className="text-xs font-medium text-slate-600 uppercase tracking-wider">
                {t('config.results')}
              </label>
              <div className="mt-2 space-y-1">
                <p className="text-sm text-slate-700">
                  <strong>{t('config.treesDetected', { count: processingJob.tree_count })}</strong>
                </p>
                {processingJob.point_count && (
                  <p className="text-sm text-slate-700">
                    <strong>{t('config.points', { count: (processingJob.point_count / 1000000).toFixed(2) })}</strong>
                  </p>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-2">
                {t('config.clickTree')}
              </p>
            </div>
          )}
        </div>
      </div>
    </Card>
    </div>
  );
};

export { LidarConfig };
export default LidarConfig;
