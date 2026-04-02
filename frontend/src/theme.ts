import type { MapTheme, ResolvedTheme } from "./types";
import { resolvePalette } from "./palettes";
import { resolveTexture } from "./textures";
import { resolveHoverConfig } from "./hover";

const DEFAULT_TEXTURE_OPACITY = 0.15;

export function resolveTheme(theme: MapTheme | undefined): ResolvedTheme {
  const hover = resolveHoverConfig(theme?.hover);
  return {
    palette: resolvePalette(theme?.palette),
    texture: resolveTexture(theme?.texture),
    textureOpacity: theme?.textureOpacity ?? DEFAULT_TEXTURE_OPACITY,
    hoverClassName: hover.className,
    hoverKeyframes: hover.keyframes,
    hoverStyle: hover.style,
  };
}
