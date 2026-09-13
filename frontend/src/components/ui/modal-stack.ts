interface ModalLayer {
  id: symbol;
  close: () => void;
}

const layers: ModalLayer[] = [];
const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

export function registerModalLayer(layer: ModalLayer): () => void {
  layers.push(layer);
  notify();
  return () => {
    const index = layers.findIndex((item) => item.id === layer.id);
    if (index !== -1) layers.splice(index, 1);
    notify();
  };
}

export function isTopModalLayer(id: symbol): boolean {
  return layers.at(-1)?.id === id;
}

export function closeTopModalLayer(): boolean {
  const layer = layers.at(-1);
  if (!layer) return false;
  layer.close();
  return true;
}

export function hasOpenModalLayer(): boolean {
  return layers.length > 0;
}

export function subscribeModalLayers(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
