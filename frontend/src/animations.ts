const zoneAnimationRegistry = new Map<number, string>();

export function animationClassForZone(zoneId: number): string {
  return zoneAnimationRegistry.get(zoneId) ?? "hover-default";
}

export function registerZoneAnimation(zoneId: number, className: string): void {
  zoneAnimationRegistry.set(zoneId, className);
}
