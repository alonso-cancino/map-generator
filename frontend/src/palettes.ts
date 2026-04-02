import * as d3 from "d3";
import type { BuiltinPalette } from "./types";

type PaletteFn = (zoneId: number, depth: number) => string;

function makeHslPalette(
  hueMin: number,
  hueMax: number,
  saturation: number,
  lightness: number,
  lightnessPerDepth: number = 0,
): PaletteFn {
  const hueRange = hueMax - hueMin;
  return (zoneId, depth) => {
    const hue = hueMin + ((zoneId * 47) % Math.max(hueRange, 1));
    const l = Math.min(lightness + depth * lightnessPerDepth, 0.85);
    return d3.hsl(hue, saturation, l).formatHex();
  };
}

const PALETTE_FUNCTIONS: Record<BuiltinPalette, PaletteFn> = {
  default: (zoneId) => {
    const hue = (zoneId * 47) % 360;
    return d3.hsl(hue, 0.48, 0.55).formatHex();
  },
  parchment: makeHslPalette(25, 55, 0.32, 0.62, 0.02),
  forest: makeHslPalette(80, 160, 0.45, 0.4, 0.03),
  ocean: makeHslPalette(180, 240, 0.5, 0.48, 0.02),
  volcanic: makeHslPalette(0, 40, 0.55, 0.38, 0.02),
  arctic: makeHslPalette(200, 230, 0.15, 0.7, 0.01),
};

export const BUILTIN_PALETTES: readonly BuiltinPalette[] = [
  "default",
  "parchment",
  "forest",
  "ocean",
  "volcanic",
  "arctic",
];

export function resolvePalette(
  palette: BuiltinPalette | ((zoneId: number, depth: number) => string) | undefined,
): PaletteFn {
  if (palette === undefined) {
    return PALETTE_FUNCTIONS.default;
  }
  if (typeof palette === "function") {
    return palette;
  }
  return PALETTE_FUNCTIONS[palette] ?? PALETTE_FUNCTIONS.default;
}
