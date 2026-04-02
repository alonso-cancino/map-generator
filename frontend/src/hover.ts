import type { BuiltinHoverPreset, CustomHoverAnimation } from "./types";

interface ResolvedHover {
  className: string;
  keyframes: string | null;
  style: Record<string, string> | null;
}

const PRESET_MAP: Record<BuiltinHoverPreset, string> = {
  pulse: "hover-pulse",
  glow: "hover-glow",
  lift: "hover-lift",
  none: "hover-none",
};

export const BUILTIN_HOVER_PRESETS: readonly BuiltinHoverPreset[] = [
  "pulse",
  "glow",
  "lift",
  "none",
];

export function resolveHoverConfig(
  hover: BuiltinHoverPreset | CustomHoverAnimation | undefined,
): ResolvedHover {
  if (hover === undefined) {
    return { className: "hover-pulse", keyframes: null, style: null };
  }
  if (typeof hover === "string") {
    return { className: PRESET_MAP[hover] ?? "hover-pulse", keyframes: null, style: null };
  }
  return {
    className: hover.className,
    keyframes: hover.keyframes ?? null,
    style: hover.style ?? null,
  };
}
