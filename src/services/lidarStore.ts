type Listener = () => void;

export type LayerScope = 'selected' | 'all';

class LidarStore {
  public selectedLayerId: string | null = null;
  public activeTilesetUrl: string | null = null;
  public colorMode: 'height' | 'ndvi' | 'rgb' | 'classification' = 'height';
  public showTrees: boolean = false;
  public heightOffset: number = -50;  // meters, negative = push down to compensate orthometric→ellipsoidal datum
  public layers: any[] = [];
  public layerVisible: boolean = false;
  public layerScope: LayerScope = 'selected';
  
  private listeners: Set<Listener> = new Set();

  subscribe(listener: Listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify() {
    this.listeners.forEach(l => l());
  }

  setLayerState(layerId: string | null, tilesetUrl: string | null) {
    this.selectedLayerId = layerId;
    this.activeTilesetUrl = tilesetUrl;
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
