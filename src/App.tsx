// =============================================================================
// LIDAR Module - NKZ Platform
// =============================================================================
// LiDAR Point Cloud Processing & Visualization Module
//
// This module provides:
// - PNOA LiDAR coverage checking and download
// - Custom .LAZ file upload from drone flights
// - 3D Tiles generation and CesiumJS visualization
// - Tree detection and analysis
//
// IMPORTANT: When loaded as a federated module, the Host provides:
// - NekazariI18nProvider (i18n context)
// - AuthProvider (authentication context)
// - Layout (navigation, sidebar)
// =============================================================================

import React from 'react';
import { Layers, Cpu, TreeDeciduous, Upload, Download, Eye, ArrowRight } from 'lucide-react';
import { useTranslation } from './sdk';
import './index.css';

// Export slots for Module Federation
export { lidarSlots, viewerSlots } from './slots';
export { LidarProvider, useLidarContext } from './services/lidarContext';
export { default as LidarLayerControl } from './components/slots/LidarLayerControl';
export { default as LidarLayer } from './components/slots/LidarLayer';
export { default as LidarConfig } from './components/slots/LidarConfig';

// Feature Card Component
const FeatureCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  description: string;
  gradient: string;
}> = ({ icon, title, description, gradient }) => (
  <div className="lidar-card p-6 group hover:scale-[1.02] transition-transform duration-300">
    <div className={`w-12 h-12 rounded-xl flex items-center justify-center mb-4 ${gradient}`}>
      {icon}
    </div>
    <h3 className="font-semibold text-slate-800 mb-2">{title}</h3>
    <p className="text-sm text-slate-600">{description}</p>
  </div>
);

// Main App Component (Landing Page)
const LidarApp: React.FC = () => {
  const { t } = useTranslation('lidar');

  const pipelineSteps = [
    { step: '01', title: t('pipeline.step1.title'), desc: t('pipeline.step1.desc') },
    { step: '02', title: t('pipeline.step2.title'), desc: t('pipeline.step2.desc') },
    { step: '03', title: t('pipeline.step3.title'), desc: t('pipeline.step3.desc') },
    { step: '04', title: t('pipeline.step4.title'), desc: t('pipeline.step4.desc') },
  ];

  return (
    <div className="lidar-module bg-gradient-to-br from-violet-50 via-white to-cyan-50 p-6 md:p-10">
      <div className="max-w-5xl mx-auto">

        {/* Hero Section */}
        <div className="text-center mb-12 lidar-slide-in">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-violet-100 text-violet-700 text-sm font-medium mb-6">
            <div className="w-2 h-2 rounded-full bg-violet-500 animate-pulse" />
            {t('premiumModule')}
          </div>

          <div className="flex items-center justify-center gap-4 mb-6">
            <div className="lidar-pointcloud-icon p-4 rounded-2xl bg-gradient-to-br from-violet-500 to-cyan-500 shadow-lg">
              <Layers className="w-10 h-10 text-white" />
            </div>
          </div>

          <h1 className="text-4xl md:text-5xl font-bold text-slate-900 mb-4">
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-600 to-cyan-600">
              {t('title')}
            </span>
          </h1>

          <p className="text-xl text-slate-600 max-w-2xl mx-auto mb-6">
            {t('subtitle')}
          </p>

          <a
            href="#/viewer"
            className="lidar-btn lidar-btn-primary inline-flex items-center gap-2"
          >
            {t('goToViewer')}
            <ArrowRight className="w-4 h-4" />
          </a>
        </div>

        {/* Features Grid */}
        <div className="grid md:grid-cols-3 gap-6 mb-12">
          <FeatureCard
            icon={<Download className="w-6 h-6 text-white" />}
            title={t('feature.download.title')}
            description={t('feature.download.desc')}
            gradient="bg-gradient-to-br from-violet-500 to-violet-600"
          />
          <FeatureCard
            icon={<Upload className="w-6 h-6 text-white" />}
            title={t('feature.upload.title')}
            description={t('feature.upload.desc')}
            gradient="bg-gradient-to-br from-cyan-500 to-cyan-600"
          />
          <FeatureCard
            icon={<TreeDeciduous className="w-6 h-6 text-white" />}
            title={t('feature.trees.title')}
            description={t('feature.trees.desc')}
            gradient="bg-gradient-to-br from-emerald-500 to-emerald-600"
          />
        </div>

        {/* Technical Specs */}
        <div className="lidar-card p-8 mb-12">
          <h2 className="text-2xl font-bold text-slate-800 mb-6 flex items-center gap-3">
            <Cpu className="w-6 h-6 text-violet-500" />
            {t('pipeline.title')}
          </h2>

          <div className="grid md:grid-cols-4 gap-6">
            {pipelineSteps.map((item, i) => (
              <div key={i} className="relative">
                <div className="text-4xl font-bold text-violet-100 mb-2">{item.step}</div>
                <h3 className="font-semibold text-slate-800 mb-1">{item.title}</h3>
                <p className="text-sm text-slate-600">{item.desc}</p>
                {i < 3 && (
                  <div className="hidden md:block absolute top-4 -right-3 text-violet-300 text-2xl">&rarr;</div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* How to Use */}
        <div className="lidar-card p-8">
          <h2 className="text-2xl font-bold text-slate-800 mb-6 flex items-center gap-3">
            <Eye className="w-6 h-6 text-cyan-500" />
            {t('howTo.title')}
          </h2>

          <div className="space-y-4">
            <div className="flex items-start gap-4 p-4 rounded-xl bg-slate-50 hover:bg-violet-50 transition-colors">
              <div className="w-8 h-8 rounded-full bg-violet-500 text-white flex items-center justify-center flex-shrink-0 font-semibold">1</div>
              <div>
                <h3 className="font-semibold text-slate-800">{t('howTo.step1.title')}</h3>
                <p className="text-sm text-slate-600">{t('howTo.step1.desc')}</p>
              </div>
            </div>

            <div className="flex items-start gap-4 p-4 rounded-xl bg-slate-50 hover:bg-cyan-50 transition-colors">
              <div className="w-8 h-8 rounded-full bg-cyan-500 text-white flex items-center justify-center flex-shrink-0 font-semibold">2</div>
              <div>
                <h3 className="font-semibold text-slate-800">{t('howTo.step2.title')}</h3>
                <p className="text-sm text-slate-600">{t('howTo.step2.desc')}</p>
              </div>
            </div>

            <div className="flex items-start gap-4 p-4 rounded-xl bg-slate-50 hover:bg-emerald-50 transition-colors">
              <div className="w-8 h-8 rounded-full bg-emerald-500 text-white flex items-center justify-center flex-shrink-0 font-semibold">3</div>
              <div>
                <h3 className="font-semibold text-slate-800">{t('howTo.step3.title')}</h3>
                <p className="text-sm text-slate-600">{t('howTo.step3.desc')}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer Note */}
        <div className="mt-8 text-center">
          <p className="text-sm text-slate-500">
            {t('footer')}
          </p>
        </div>
      </div>
    </div>
  );
};

// CRITICAL: Export as default - required for Module Federation
export default LidarApp;
