/**
 * Type definitions for the LiDAR module
 */

// ============================================================================
// GeoJSON Types
// ============================================================================

export interface GeoJSONPoint {
  type: 'Point';
  coordinates: [number, number];
}

export interface GeoJSONLineString {
  type: 'LineString';
  coordinates: number[][];
}

export interface GeoJSONPolygon {
  type: 'Polygon';
  coordinates: number[][][];
}

export interface GeoJSONMultiPolygon {
  type: 'MultiPolygon';
  coordinates: number[][][][];
}

export type GeoJSONGeometry =
  | GeoJSONPoint
  | GeoJSONLineString
  | GeoJSONPolygon
  | GeoJSONMultiPolygon;

// ============================================================================
// Cesium Types (subset used by this module)
// ============================================================================

export interface CesiumViewer {
  scene: {
    primitives: {
      add: (primitive: CesiumTileset) => CesiumTileset;
      remove: (primitive: CesiumTileset) => boolean;
    };
    postProcessStages: {
      ambientOcclusion: unknown;
    };
  };
  flyTo: (target: CesiumTileset, options?: Record<string, unknown>) => void;
  isDestroyed: () => boolean;
}

export interface CesiumTileset {
  style: unknown;
  readyPromise?: Promise<void>;
}

// ============================================================================
// Window Globals (injected by host)
// ============================================================================

export interface NekazariAuthContext {
  user: Record<string, unknown> | null;
  token?: string;
  tenantId?: string;
  roles?: string[];
}

export interface NekazariViewerContext {
  useViewer: () => ViewerHookResult;
}

export interface ViewerHookResult {
  selectedEntityId: string | null;
  selectedEntityType: string | null;
  currentDate: Date;
  isTimelinePlaying: boolean;
  activeLayers: Set<string>;
  isLayerActive: (layer: string) => boolean;
  setLayerActive: (layer: string, active: boolean) => void;
  toggleLayer: (layer: string) => void;
  selectEntity: (id: string | null, type?: string | null) => void;
  setCurrentDate: (date: Date) => void;
}

export interface NekazariI18nContext {
  t: (key: string, params?: Record<string, string | number>) => string;
  i18n: {
    language: string;
  };
}

// UI Kit component prop types
export interface CardProps {
  children: React.ReactNode;
  className?: string;
  padding?: 'sm' | 'md' | 'lg';
}

export interface ButtonProps {
  children: React.ReactNode;
  variant?: 'primary' | 'danger' | 'ghost' | 'default';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  onClick?: () => void;
  className?: string;
}

export interface UIKit {
  Card: React.FC<CardProps>;
  Button: React.FC<ButtonProps>;
  Input?: React.FC<React.InputHTMLAttributes<HTMLInputElement>>;
  Select?: React.FC<React.SelectHTMLAttributes<HTMLSelectElement>>;
}

// Tree data
export interface TreeData {
  id: string;
  height: number;
  crownDiameter: number;
  crownArea: number;
  ndviMean?: number;
  location: GeoJSONPoint;
}

declare global {
  interface Window {
    __nekazariAuth?: NekazariAuthContext;
    __nekazariAuthContext?: NekazariAuthContext;
    __nekazariViewerContext?: NekazariViewerContext;
    __nekazariUIKit?: UIKit;
    __nekazariI18n?: NekazariI18nContext;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    Cesium?: any;
    keycloak?: {
      token?: string;
      tokenParsed?: Record<string, unknown>;
    };
  }
}
