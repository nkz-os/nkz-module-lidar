/**
 * TreeInfo - Tree Information Popup/Panel Component
 *
 * Displays detailed information about a detected tree entity.
 * Used in the context panel when a tree marker is clicked.
 */

import React from 'react';
import { TreeDeciduous, Ruler, Circle, Leaf, MapPin } from 'lucide-react';
import { useUIKit } from '../../hooks/useUIKit';
import { useTranslation } from '../../sdk';
import type { TreeData } from '../../types';

interface TreeInfoProps {
    tree: TreeData | null;
    onClose?: () => void;
}

const TreeInfo: React.FC<TreeInfoProps> = ({ tree, onClose }) => {
    const { Card } = useUIKit();
    const { t } = useTranslation('lidar');

    if (!tree) {
        return null;
    }

    // Health status based on NDVI
    const getHealthStatus = (ndvi?: number) => {
        if (ndvi === undefined) return { label: t('tree.health.unknown'), color: 'text-slate-500', bg: 'bg-slate-100' };
        if (ndvi >= 0.6) return { label: t('tree.health.excellent'), color: 'text-green-700', bg: 'bg-green-100' };
        if (ndvi >= 0.4) return { label: t('tree.health.good'), color: 'text-emerald-700', bg: 'bg-emerald-100' };
        if (ndvi >= 0.2) return { label: t('tree.health.fair'), color: 'text-yellow-700', bg: 'bg-yellow-100' };
        return { label: t('tree.health.poor'), color: 'text-red-700', bg: 'bg-red-100' };
    };

    const healthStatus = getHealthStatus(tree.ndviMean);

    return (
        <Card padding="md" className="bg-white/95 backdrop-blur-md border border-slate-200/50 rounded-xl shadow-lg w-72">
            <div className="space-y-4">
                {/* Header */}
                <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                    <h3 className="font-semibold text-slate-800 flex items-center gap-2">
                        <TreeDeciduous className="w-5 h-5 text-green-600" />
                        {t('tree.title')}
                    </h3>
                    {onClose && (
                        <button
                            onClick={onClose}
                            className="text-slate-400 hover:text-slate-600 transition-colors"
                        >
                            &times;
                        </button>
                    )}
                </div>

                {/* Tree ID */}
                <div className="text-xs text-slate-500 font-mono bg-slate-50 px-2 py-1 rounded">
                    ID: {tree.id}
                </div>

                {/* Health Status Badge */}
                <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full ${healthStatus.bg}`}>
                    <Leaf className={`w-4 h-4 ${healthStatus.color}`} />
                    <span className={`text-sm font-medium ${healthStatus.color}`}>
                        {t('tree.health.label')}: {healthStatus.label}
                    </span>
                </div>

                {/* Metrics Grid */}
                <div className="grid grid-cols-2 gap-3">
                    {/* Height */}
                    <div className="bg-slate-50 rounded-lg p-3">
                        <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                            <Ruler className="w-3.5 h-3.5" />
                            <span className="text-xs font-medium">{t('tree.height')}</span>
                        </div>
                        <div className="text-lg font-bold text-slate-800">
                            {tree.height.toFixed(1)} <span className="text-sm font-normal text-slate-500">m</span>
                        </div>
                    </div>

                    {/* Crown Diameter */}
                    <div className="bg-slate-50 rounded-lg p-3">
                        <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                            <Circle className="w-3.5 h-3.5" />
                            <span className="text-xs font-medium">{t('tree.crownDiameter')}</span>
                        </div>
                        <div className="text-lg font-bold text-slate-800">
                            {tree.crownDiameter.toFixed(1)} <span className="text-sm font-normal text-slate-500">m</span>
                        </div>
                    </div>

                    {/* Crown Area */}
                    <div className="bg-slate-50 rounded-lg p-3">
                        <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                            <TreeDeciduous className="w-3.5 h-3.5" />
                            <span className="text-xs font-medium">{t('tree.crownArea')}</span>
                        </div>
                        <div className="text-lg font-bold text-slate-800">
                            {tree.crownArea.toFixed(1)} <span className="text-sm font-normal text-slate-500">m&sup2;</span>
                        </div>
                    </div>

                    {/* NDVI */}
                    <div className="bg-slate-50 rounded-lg p-3">
                        <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                            <Leaf className="w-3.5 h-3.5" />
                            <span className="text-xs font-medium">{t('tree.ndvi')}</span>
                        </div>
                        <div className="text-lg font-bold text-slate-800">
                            {tree.ndviMean !== undefined ? tree.ndviMean.toFixed(2) : '\u2014'}
                        </div>
                    </div>
                </div>

                {/* Location */}
                <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2">
                    <MapPin className="w-3.5 h-3.5" />
                    <span>
                        {tree.location.coordinates[1].toFixed(6)}, {tree.location.coordinates[0].toFixed(6)}
                    </span>
                </div>

                {/* Estimated Biomass (calculated from height and crown) */}
                <div className="border-t border-slate-100 pt-3">
                    <div className="text-xs text-slate-500 mb-1">{t('tree.biomass')}</div>
                    <div className="text-sm font-medium text-slate-700">
                        ~{Math.round(tree.height * tree.crownArea * 0.5)} kg
                        <span className="text-xs text-slate-400 ml-1">{t('tree.biomassApprox')}</span>
                    </div>
                </div>
            </div>
        </Card>
    );
};

export default TreeInfo;
