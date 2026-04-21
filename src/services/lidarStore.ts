type Listener = () => void;

class LidarStore {
  public selectedLayerId: string | null = null;
  public activeTilesetUrl: string | null = null;
  public colorMode: 'height' | 'ndvi' | 'rgb' | 'classification' = 'height';
  public showTrees: boolean = false;
  public layers: any[] = [];
  
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

  setLayers(layers: any[]) {
    this.layers = layers;
    this.notify();
  }
}

export const lidarStore = new LidarStore();
