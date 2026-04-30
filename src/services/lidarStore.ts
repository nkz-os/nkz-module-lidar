type Listener = () => void;

class LidarStore {
  public selectedLayerId: string | null = null;
  public activeTilesetUrl: string | null = null;
  public colorMode: 'height' | 'classification' | 'heightAboveGround' | 'canopyCover' | 'verticalDensity' | 'rgb' = 'height';
  public showTrees: boolean = false;
  public heightOffset: number = -50;  // meters, negative = push down to compensate orthometric→ellipsoidal datum
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

  setColorMode(mode: 'height' | 'classification' | 'heightAboveGround' | 'canopyCover' | 'verticalDensity' | 'rgb') {
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
}

export const lidarStore = new LidarStore();
