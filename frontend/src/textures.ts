import type { BuiltinTexture, SvgPatternDef } from "./types";

const TEXTURE_DEFS: Record<Exclude<BuiltinTexture, "none">, SvgPatternDef> = {
  crosshatch: {
    id: "zone-texture-crosshatch",
    width: 8,
    height: 8,
    content: [
      '<line x1="0" y1="0" x2="8" y2="8" stroke="currentColor" stroke-width="0.5" />',
      '<line x1="8" y1="0" x2="0" y2="8" stroke="currentColor" stroke-width="0.5" />',
    ].join(""),
  },
  dots: {
    id: "zone-texture-dots",
    width: 6,
    height: 6,
    content: '<circle cx="3" cy="3" r="0.8" fill="currentColor" />',
  },
  waves: {
    id: "zone-texture-waves",
    width: 12,
    height: 6,
    content:
      '<path d="M0 3 Q3 0, 6 3 Q9 6, 12 3" fill="none" stroke="currentColor" stroke-width="0.5" />',
  },
  "parchment-noise": {
    id: "zone-texture-parchment-noise",
    width: 10,
    height: 10,
    content: [
      '<rect x="1" y="2" width="1" height="1" fill="currentColor" opacity="0.4" />',
      '<rect x="5" y="7" width="1.2" height="0.8" fill="currentColor" opacity="0.3" />',
      '<rect x="8" y="1" width="0.8" height="1.2" fill="currentColor" opacity="0.35" />',
      '<rect x="3" y="5" width="1" height="0.6" fill="currentColor" opacity="0.25" />',
      '<rect x="7" y="4" width="0.6" height="1" fill="currentColor" opacity="0.3" />',
      '<rect x="2" y="8" width="0.9" height="0.9" fill="currentColor" opacity="0.35" />',
    ].join(""),
  },
  stipple: {
    id: "zone-texture-stipple",
    width: 8,
    height: 8,
    content: [
      '<circle cx="1" cy="3" r="0.5" fill="currentColor" opacity="0.4" />',
      '<circle cx="5" cy="1" r="0.4" fill="currentColor" opacity="0.35" />',
      '<circle cx="3" cy="6" r="0.45" fill="currentColor" opacity="0.3" />',
      '<circle cx="7" cy="5" r="0.5" fill="currentColor" opacity="0.38" />',
      '<circle cx="4" cy="8" r="0.35" fill="currentColor" opacity="0.32" />',
    ].join(""),
  },
};

export const BUILTIN_TEXTURES: readonly BuiltinTexture[] = [
  "none",
  "crosshatch",
  "dots",
  "waves",
  "parchment-noise",
  "stipple",
];

export function resolveTexture(
  texture: BuiltinTexture | SvgPatternDef | undefined,
): SvgPatternDef | null {
  if (texture === undefined || texture === "none") {
    return null;
  }
  if (typeof texture === "object") {
    return texture;
  }
  return TEXTURE_DEFS[texture] ?? null;
}
