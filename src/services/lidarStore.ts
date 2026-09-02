type Listener = () => void;

export type LayerScope = 'selected' | 'all';

export interface AutoFitStatus {
  state: 'idle' | 'busy' | 'done' | 'error';
  message?: string;
  offset?: number;
}

const OFFSET_STORAGE_PREFIX = 'nkz:lidar:heightOffset:';

// Fallback offset (m) approximating the orthometric→ellipsoidal geoid
// separation over Spain for layers processed before the compound-CRS fix.
const LEGACY_DEFAULT_OFFSET = -50;

function storageAvailable(): boolean {
  try {
    return typeof localStorage !== 'undefined';
  } catch {
    return false;
  }
}

class LidarStore {
  public selectedLayerId: string | null = null;
  public activeTilesetUrl: string | null = null;
  public colorMode: 'height' | 'ndvi' | 'rgb' | 'classification' = 'height';
  public showTrees: boolean = false;
  public heightOffset: number = LEGACY_DEFAULT_OFFSET;  // meters; 0 for datum-fixed layers
  public layers: any[] = [];
  public layerVisible: boolean = false;
  public layerScope: LayerScope = 'selected';
  public autoFitToken: number = 0;
  public autoFitStatus: AutoFitStatus = { state: 'idle' };

  private listeners: Set<Listener> = new Set();

  subscribe(listener: Listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify() {
    this.listeners.forEach(l => l());
  }

  /**
   * Default offset for a layer: layers processed with a verified vertical
   * datum (verticalReference present) render correctly at 0; legacy layers
   * (orthometric Z treated as ellipsoidal) keep the approximate geoid offset.
   */
  private defaultOffsetFor(layerId: string | null): number {
    if (!layerId) return LEGACY_DEFAULT_OFFSET;
    const layer = this.layers.find((l: any) => l.id === layerId);
    return layer?.vertical_reference ? 0 : LEGACY_DEFAULT_OFFSET;
  }

  private loadPersistedOffset(layerId: string | null): number | null {
    if (!layerId || !storageAvailable()) return null;
    const raw = localStorage.getItem(OFFSET_STORAGE_PREFIX + layerId);
    if (raw === null) return null;
    const value = parseFloat(raw);
    return Number.isFinite(value) ? value : null;
  }

  setLayerState(layerId: string | null, tilesetUrl: string | null) {
    this.selectedLayerId = layerId;
    this.activeTilesetUrl = tilesetUrl;
    // Per-layer offset: user-refined value > datum-aware default.
    this.heightOffset = this.loadPersistedOffset(layerId) ?? this.defaultOffsetFor(layerId);
    this.autoFitStatus = { state: 'idle' };
    this.notify();
  }

  setColorMode(mode: 'height' | 'ndvi' | 'rgb' | 'classification') {
    this.colorMode = mode;
    this.notify();
  }

  setShowTrees(show: boolean) {
    this.showTrees = show;
    this.notify();
  }

  setHeightOffset(offset: number) {
    this.heightOffset = offset;
    if (this.selectedLayerId && storageAvailable() && Number.isFinite(offset)) {
      localStorage.setItem(OFFSET_STORAGE_PREFIX + this.selectedLayerId, String(offset));
    }
    this.notify();
  }

  requestAutoFit() {
    this.autoFitToken += 1;
    this.autoFitStatus = { state: 'busy' };
    this.notify();
  }

  setAutoFitStatus(status: AutoFitStatus) {
    this.autoFitStatus = status;
    this.notify();
  }

  setLayers(layers: any[]) {
    this.layers = layers;
    this.notify();
  }

  setLayerVisible(visible: boolean) {
    this.layerVisible = visible;
    this.notify();
  }

  setLayerScope(scope: LayerScope) {
    this.layerScope = scope;
    this.notify();
  }
}

export const lidarStore = new LidarStore();
