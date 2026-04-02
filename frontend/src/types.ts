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

export type DetailCommitMode = "animation-frame" | "interaction-end";

export interface MapRenderConfig {
  detailCommitMode: DetailCommitMode;
  interactionSettleMs: number;
  disableEffectsWhileInteracting: boolean;
}

// --- Color Palette ---

export type BuiltinPalette = "default" | "parchment" | "forest" | "ocean" | "volcanic" | "arctic";

// --- Texture ---

export type BuiltinTexture = "none" | "crosshatch" | "dots" | "waves" | "parchment-noise" | "stipple";

export interface SvgPatternDef {
  id: string;
  width: number;
  height: number;
  /** SVG markup string for the pattern content */
  content: string;
}

// --- Hover Animation ---

export type BuiltinHoverPreset = "pulse" | "glow" | "lift" | "none";

export interface CustomHoverAnimation {
  /** CSS class name to apply when hovered */
  className: string;
  /** CSS keyframes definition string (injected into a <style> tag) */
  keyframes?: string;
  /** Inline CSS properties applied on hover */
  style?: Record<string, string>;
}

// --- Theme ---

export interface MapTheme {
  palette?: BuiltinPalette | ((zoneId: number, depth: number) => string);
  texture?: BuiltinTexture | SvgPatternDef;
  textureOpacity?: number;
  hover?: BuiltinHoverPreset | CustomHoverAnimation;
}

// --- Side Panel ---

export type PanelState = "hidden" | "half" | "full";

export interface SidePanelConfig {
  enabled: boolean;
  defaultState?: PanelState;
  state?: PanelState;
  onStateChange?: (state: PanelState) => void;
  position?: "left" | "right";
}

// --- Resolved Theme (internal) ---

export interface ResolvedTheme {
  palette: (zoneId: number, depth: number) => string;
  texture: SvgPatternDef | null;
  textureOpacity: number;
  hoverClassName: string;
  hoverKeyframes: string | null;
  hoverStyle: Record<string, string> | null;
}

export interface MapViewProps {
  bundle: FrontendBundle;
  renderConfig?: Partial<MapRenderConfig>;
  theme?: MapTheme;
  panel?: SidePanelConfig;
  panelContent?: React.ReactNode;
  onZoneClick?: (zone: ZoneRecord) => void;
  onZoneHover?: (zone: ZoneRecord | null) => void;
}
