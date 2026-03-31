export interface RawZoneRecord {
  id: number;
  name: string;
  parent_id: number | null;
  depth: number;
  child_ids: number[];
  is_leaf: boolean;
  bbox: [number, number, number, number];
  area: number;
  path: string;
  children_reveal_depth: number | null;
}

export interface RawBorderRecord {
  id: string;
  zone_ids: [number, number];
  path: string;
}

export interface RawFrontendBundle {
  root_id: number;
  max_depth: number;
  world_bbox: [number, number, number, number];
  zoom_depth_thresholds: Record<string, number>;
  levels: Record<string, number[]>;
  borders: RawBorderRecord[];
  zones: Record<string, RawZoneRecord>;
}

export interface BorderRecord {
  id: string;
  zoneIds: [number, number];
  path: string;
}

export interface ZoneRecord {
  id: number;
  name: string;
  parentId: number | null;
  depth: number;
  childIds: number[];
  isLeaf: boolean;
  bbox: [number, number, number, number];
  area: number;
  path: string;
  childrenRevealDepth: number | null;
}

export interface FrontendBundle {
  rootId: number;
  maxDepth: number;
  worldBBox: [number, number, number, number];
  zoomDepthThresholds: Map<number, number>;
  levels: Map<number, number[]>;
  borders: BorderRecord[];
  zones: Map<number, ZoneRecord>;
}
