import type { FrontendBundle, RawFrontendBundle, ZoneRecord } from "./types";

export async function loadBundle(path: string): Promise<FrontendBundle> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to load map bundle from ${path}: ${response.status}`);
  }
  const raw = (await response.json()) as RawFrontendBundle;
  return parseBundle(raw);
}

export function parseBundle(raw: RawFrontendBundle): FrontendBundle {
  const zones = new Map<number, ZoneRecord>();
  for (const zone of Object.values(raw.zones)) {
    zones.set(zone.id, {
      id: zone.id,
      name: zone.name,
      parentId: zone.parent_id,
      depth: zone.depth,
      childIds: zone.child_ids,
      isLeaf: zone.is_leaf,
      bbox: zone.bbox,
      area: zone.area,
      path: zone.path,
      childrenRevealDepth: zone.children_reveal_depth,
    });
  }

  const levels = new Map<number, number[]>();
  for (const [depth, zoneIds] of Object.entries(raw.levels)) {
    levels.set(Number(depth), zoneIds);
  }

  const zoomDepthThresholds = new Map<number, number>();
  for (const [depth, threshold] of Object.entries(raw.zoom_depth_thresholds)) {
    zoomDepthThresholds.set(Number(depth), threshold);
  }

  return {
    borders: (raw.borders ?? []).map((border) => ({
      id: border.id,
      zoneIds: border.zone_ids,
      path: border.path,
    })),
    rootId: raw.root_id,
    maxDepth: raw.max_depth,
    worldBBox: raw.world_bbox,
    levels,
    zones,
    zoomDepthThresholds,
  };
}
