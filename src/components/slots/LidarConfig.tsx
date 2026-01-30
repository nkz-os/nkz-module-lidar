/**
 * LIDAR Config - Context panel component for tree details
 * 
 * Shows when a parcel is selected and displays configuration
 * and tree information when trees are detected.
 */

import React from 'react';
import { useUIKit } from '../../hooks/useUIKit';
import { useLidarContext } from '../../services/lidarContext';
import TreeInfo from './TreeInfo';

interface LidarConfigProps {
  selectedTree?: any;  // Tree data from map click
}

const LidarConfig: React.FC<LidarConfigProps> = ({ selectedTree }) => {
  const { Card } = useUIKit();
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
    <Card padding="md" className="bg-white/90 backdrop-blur-md border border-slate-200/50 rounded-xl">
      <div className="space-y-4">
        <h3 className="font-semibold text-slate-800">Configuración LIDAR</h3>

        <div className="space-y-3">
          {/* Parcel Info */}
          <div>
            <label className="text-xs font-medium text-slate-600 uppercase tracking-wider">
              Parcela
            </label>
            <p className="text-sm text-slate-800 mt-1 font-mono truncate">
              {selectedEntityId.split(':').pop()}
            </p>
          </div>

          {/* Layer Status */}
          {activeTilesetUrl && (
            <div>
              <label className="text-xs font-medium text-slate-600 uppercase tracking-wider">
                Capa activa
              </label>
              <div className="flex items-center gap-2 mt-1">
                <div className="w-2 h-2 rounded-full bg-green-500"></div>
                <span className="text-sm text-green-700">Nube de puntos cargada</span>
              </div>
            </div>
          )}

          {/* Color Mode */}
          {activeTilesetUrl && (
            <div>
              <label className="text-xs font-medium text-slate-600 uppercase tracking-wider">
                Modo de visualización
              </label>
              <p className="text-sm text-slate-800 mt-1 capitalize">
                {colorMode === 'ndvi' ? 'NDVI (Vigor)' :
                  colorMode === 'height' ? 'Altura' :
                    colorMode === 'rgb' ? 'Color Real' :
                      colorMode === 'classification' ? 'Clasificación' : colorMode}
              </p>
            </div>
          )}

          {/* Processing Status */}
          {processingJob && processingJob.status !== 'completed' && (
            <div>
              <label className="text-xs font-medium text-slate-600 uppercase tracking-wider">
                Estado del procesamiento
              </label>
              <p className="text-sm text-slate-800 mt-1">
                {processingJob.status_message || processingJob.status}
              </p>
              {processingJob.tree_count !== undefined && processingJob.tree_count > 0 && (
                <p className="text-xs text-green-600 mt-1">
                  🌳 {processingJob.tree_count} árboles detectados
                </p>
              )}
            </div>
          )}

          {/* Results Summary */}
          {processingJob?.status === 'completed' && processingJob.tree_count !== undefined && (
            <div className="border-t border-slate-100 pt-3">
              <label className="text-xs font-medium text-slate-600 uppercase tracking-wider">
                Resultados
              </label>
              <div className="mt-2 space-y-1">
                <p className="text-sm text-slate-700">
                  🌳 <strong>{processingJob.tree_count}</strong> árboles detectados
                </p>
                {processingJob.point_count && (
                  <p className="text-sm text-slate-700">
                    📍 <strong>{(processingJob.point_count / 1000000).toFixed(2)}M</strong> puntos
                  </p>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-2">
                Haz clic en un árbol en el mapa para ver detalles
              </p>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
};

export { LidarConfig };
export default LidarConfig;


