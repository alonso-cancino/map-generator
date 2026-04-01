import type { Dispatch, MutableRefObject, RefObject, SetStateAction } from "react";
import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import { animationClassForZone } from "./animations";
import type {
  BorderRecord,
  FrontendBundle,
  MapRenderConfig,
  MapViewProps,
  ZoneRecord,
} from "./types";

interface ViewportSize {
  width: number;
  height: number;
}

interface PointerPosition {
  x: number;
  y: number;
}

const PADDING = 48;
const DEFAULT_RENDER_CONFIG: MapRenderConfig = {
  detailCommitMode: "animation-frame",
  interactionSettleMs: 80,
  disableEffectsWhileInteracting: true,
};

export function MapView({ bundle, renderConfig }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const rootLayerRef = useRef<SVGGElement | null>(null);
  const regionElementsRef = useRef(new Map<number, SVGPathElement>());
  const hoverArmedRef = useRef(false);
  const initialViewAppliedRef = useRef(false);
  const latestTransformRef = useRef(d3.zoomIdentity);
  const animationFrameRef = useRef<number | null>(null);
  const settleTimeoutRef = useRef<number | null>(null);
  const [viewport, setViewport] = useState<ViewportSize>({ width: 960, height: 720 });
  const [committedTransform, setCommittedTransform] = useState(d3.zoomIdentity);
  const [isInteracting, setIsInteracting] = useState(false);
  const minimumDepth = minVisibleDepth(bundle);
  const [hoveredZoneId, setHoveredZoneId] = useState<number | null>(null);
  const [pointerPosition, setPointerPosition] = useState<PointerPosition | null>(null);
  const initialFocusZoneId = firstZoneAtDepth(bundle, minimumDepth) ?? bundle.rootId;
  const [focusedZoneId, setFocusedZoneId] = useState<number | null>(null);
  const visibleZones = resolveVisibleZones(bundle, committedTransform.k, viewport);
  const visibleZoneIds = new Set(visibleZones.map((zone) => zone.id));
  const visibleBorders = bundle.borders.filter(
    (border) => visibleZoneIds.has(border.zoneIds[0]) && visibleZoneIds.has(border.zoneIds[1]),
  );
  const hoveredZone = hoveredZoneId === null ? null : bundle.zones.get(hoveredZoneId) ?? null;
  const resolvedRenderConfig = resolveRenderConfig(renderConfig);

  useEffect(() => {
    initialViewAppliedRef.current = false;
    latestTransformRef.current = d3.zoomIdentity;
    setCommittedTransform(d3.zoomIdentity);
    setFocusedZoneId(null);
    setHoveredZoneId(null);
    setPointerPosition(null);
    setIsInteracting(false);
    regionElementsRef.current.clear();
  }, [bundle]);

  useEffect(() => {
    if (hoveredZoneId !== null && !visibleZoneIds.has(hoveredZoneId)) {
      setHoveredZoneId(null);
      setPointerPosition(null);
    }
  }, [hoveredZoneId, visibleZoneIds]);

  useEffect(() => {
    if (containerRef.current === null) {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry === undefined) {
        return;
      }
      const width = Math.max(Math.round(entry.contentRect.width), 320);
      const height = Math.max(Math.round(entry.contentRect.height), 480);
      setViewport({ width, height });
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (svgRef.current === null) {
      return;
    }

    const selection = d3.select(svgRef.current);
    const zoomBehavior = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([1, Math.max(2 ** (bundle.maxDepth + 2), 8)])
      .on("start", () => {
        clearSettleTimeout(settleTimeoutRef);
        setIsInteracting(true);
      })
      .on("zoom", (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
        latestTransformRef.current = event.transform;
        applyLiveTransform(rootLayerRef.current, event.transform);
        scheduleCommittedTransform(
          latestTransformRef,
          resolvedRenderConfig,
          animationFrameRef,
          settleTimeoutRef,
          setCommittedTransform,
          setIsInteracting,
        );
      })
      .on("end", (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
        latestTransformRef.current = event.transform;
        applyLiveTransform(rootLayerRef.current, event.transform);
        flushCommittedTransform(
          event.transform,
          animationFrameRef,
          settleTimeoutRef,
          resolvedRenderConfig,
          setCommittedTransform,
          setIsInteracting,
        );
      });

    zoomRef.current = zoomBehavior;
    selection.call(zoomBehavior);

    return () => {
      selection.on(".zoom", null);
      clearScheduledWork(animationFrameRef, settleTimeoutRef);
    };
  }, [bundle, resolvedRenderConfig]);

  useEffect(() => {
    if (
      initialViewAppliedRef.current ||
      svgRef.current === null ||
      zoomRef.current === null ||
      viewport.width <= 0 ||
      viewport.height <= 0
    ) {
      return;
    }
    const initialBBox = combinedBBox(visibleZones);
    if (initialBBox === null) {
      return;
    }
    initialViewAppliedRef.current = true;
    hoverArmedRef.current = false;
    setHoveredZoneId(null);
    setPointerPosition(null);
    d3.select(svgRef.current).call(
      zoomRef.current.transform,
      fitBBoxTransform(initialBBox, viewport),
    );
  }, [bundle, minimumDepth, viewport, visibleZones]);

  useEffect(() => {
    if (svgRef.current === null) {
      return;
    }
    const svg = d3.select(svgRef.current);
    svg
      .attr("viewBox", `0 0 ${viewport.width} ${viewport.height}`)
      .attr("data-interacting", isInteracting ? "true" : "false");

    const rootLayer = ensureSvgLayer(svg, "root-layer");
    rootLayerRef.current = rootLayer.node();
    applyLiveTransform(rootLayerRef.current, latestTransformRef.current);

    const sceneLayer = ensureGroupLayer(rootLayer, "scene-layer");
    sceneLayer.attr("transform", baseSceneTransform(viewport));

    const fillLayer = ensureGroupLayer(sceneLayer, "fill-layer");
    const borderLayer = ensureGroupLayer(sceneLayer, "border-layer");
    const activeOutlineLayer = ensureGroupLayer(sceneLayer, "active-outline-layer");

    const regionSelection = fillLayer
      .selectAll<SVGPathElement, ZoneRecord>("path.region")
      .data(visibleZones, (datum) => datum.id);

    regionSelection
      .join(
        (enter: d3.Selection<d3.EnterElement, ZoneRecord, SVGGElement, unknown>) =>
          enter
            .append("path")
            .attr("class", "region")
            .attr("fill-rule", "evenodd")
            .attr("vector-effect", "non-scaling-stroke"),
        (update: d3.Selection<SVGPathElement, ZoneRecord, SVGGElement, unknown>) => update,
        (exit: d3.Selection<SVGPathElement, ZoneRecord, SVGGElement, unknown>) => exit.remove(),
      )
      .attr("d", (datum: ZoneRecord) => datum.path)
      .attr("data-zone-id", (datum: ZoneRecord) => String(datum.id))
      .attr("fill", (datum: ZoneRecord) => zoneColor(datum.id))
      .attr("class", (datum: ZoneRecord) =>
        zoneClassName(datum, hoveredZoneId, focusedZoneId, isInteracting, resolvedRenderConfig),
      )
      .each(function cacheRegionElement(datum: ZoneRecord) {
        regionElementsRef.current.set(datum.id, this);
      })
      .on("click", (_: MouseEvent, datum: ZoneRecord) => {
        focusZone(datum.id, bundle, viewport, svgRef, zoomRef, setFocusedZoneId);
      });

    const currentVisibleZoneIds = new Set(visibleZones.map((zone) => zone.id));
    for (const zoneId of Array.from(regionElementsRef.current.keys())) {
      if (!currentVisibleZoneIds.has(zoneId)) {
        regionElementsRef.current.delete(zoneId);
      }
    }

    const borderSelection = borderLayer
      .selectAll<SVGPathElement, BorderRecord>("path.region-border")
      .data(visibleBorders, (datum) => datum.id);

    borderSelection
      .join(
        (enter: d3.Selection<d3.EnterElement, BorderRecord, SVGGElement, unknown>) =>
          enter
            .append("path")
            .attr("class", "region-border")
            .attr("fill", "none")
            .attr("vector-effect", "non-scaling-stroke")
            .attr("pointer-events", "none"),
        (update: d3.Selection<SVGPathElement, BorderRecord, SVGGElement, unknown>) => update,
        (exit: d3.Selection<SVGPathElement, BorderRecord, SVGGElement, unknown>) => exit.remove(),
      )
      .attr("d", (datum: BorderRecord) => datum.path)
      .attr("class", (datum: BorderRecord) =>
        borderClassName(
          datum,
          hoveredZoneId,
          focusedZoneId,
          isInteracting,
          resolvedRenderConfig,
        ),
      );

    const activeZoneId = hoveredZoneId ?? focusedZoneId;
    const activeZone =
      activeZoneId === null ? null : visibleZones.find((zone) => zone.id === activeZoneId) ?? null;
    const activeOutlineData = activeZone === null ? [] : [activeZone];

    const activeOutlineSelection = activeOutlineLayer
      .selectAll<SVGPathElement, ZoneRecord>("path.active-outline")
      .data(activeOutlineData, (datum) => datum.id);

    activeOutlineSelection
      .join(
        (enter: d3.Selection<d3.EnterElement, ZoneRecord, SVGGElement, unknown>) =>
          enter
            .append("path")
            .attr("class", "active-outline")
            .attr("fill", "none")
            .attr("fill-rule", "evenodd")
            .attr("vector-effect", "non-scaling-stroke")
            .attr("pointer-events", "none"),
        (update: d3.Selection<SVGPathElement, ZoneRecord, SVGGElement, unknown>) => update,
        (exit: d3.Selection<SVGPathElement, ZoneRecord, SVGGElement, unknown>) => exit.remove(),
      )
      .attr("d", (datum: ZoneRecord) => datum.path)
      .attr("class", (datum: ZoneRecord) =>
        activeOutlineClassName(
          datum,
          hoveredZoneId,
          focusedZoneId,
          isInteracting,
          resolvedRenderConfig,
        ),
      );

    svg
      .on("mousemove.hoverhit", (event: MouseEvent) => {
        if (!hoverArmedRef.current && event.movementX === 0 && event.movementY === 0) {
          return;
        }
        hoverArmedRef.current = true;
        const bounds = containerRef.current?.getBoundingClientRect();
        if (bounds === undefined) {
          return;
        }
        setPointerPosition({
          x: event.clientX - bounds.left,
          y: event.clientY - bounds.top,
        });
        setHoveredZoneId(hitTestVisibleZone(event, visibleZones, regionElementsRef.current));
      })
      .on("mouseleave.hoverhit", () => {
        hoverArmedRef.current = false;
        setHoveredZoneId(null);
        setPointerPosition(null);
      });

    return () => {
      svg.on("mousemove.hoverhit", null).on("mouseleave.hoverhit", null);
    };
  }, [
    bundle,
    focusedZoneId,
    hoveredZoneId,
    isInteracting,
    resolvedRenderConfig,
    viewport,
    visibleBorders,
    visibleZones,
  ]);

  return (
    <div className="map-shell">
      <div className="map-toolbar">
        <button
          className="map-button"
          type="button"
          onClick={() =>
            focusZone(initialFocusZoneId, bundle, viewport, svgRef, zoomRef, setFocusedZoneId)
          }
        >
          Reset View
        </button>
      </div>
      <div className="map-viewport" ref={containerRef}>
        <svg ref={svgRef} className="map-svg" aria-label="Hierarchical map" />
        {hoveredZone !== null && pointerPosition !== null ? (
          <div
            className="map-tooltip"
            style={{
              left: `${pointerPosition.x + 14}px`,
              top: `${pointerPosition.y + 14}px`,
            }}
          >
            {formatZoneName(hoveredZone.name)}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default MapView;

function ensureSvgLayer(
  selection: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  className: string,
) {
  const existing = selection.select<SVGGElement>(`g.${className}`);
  if (!existing.empty()) {
    return existing;
  }
  return selection.append("g").attr("class", className);
}

function ensureGroupLayer(
  selection: d3.Selection<SVGGElement, unknown, null, undefined>,
  className: string,
) {
  const existing = selection.select<SVGGElement>(`g.${className}`);
  if (!existing.empty()) {
    return existing;
  }
  return selection.append("g").attr("class", className);
}

function applyLiveTransform(layer: SVGGElement | null, transform: d3.ZoomTransform) {
  if (layer !== null) {
    d3.select(layer).attr("transform", transform.toString());
  }
}

function resolveRenderConfig(
  renderConfig: Partial<MapRenderConfig> | undefined,
): MapRenderConfig {
  return {
    ...DEFAULT_RENDER_CONFIG,
    ...renderConfig,
  };
}

function clearScheduledWork(
  animationFrameRef: MutableRefObject<number | null>,
  settleTimeoutRef: MutableRefObject<number | null>,
) {
  if (animationFrameRef.current !== null) {
    window.cancelAnimationFrame(animationFrameRef.current);
    animationFrameRef.current = null;
  }
  clearSettleTimeout(settleTimeoutRef);
}

function clearSettleTimeout(settleTimeoutRef: MutableRefObject<number | null>) {
  if (settleTimeoutRef.current !== null) {
    window.clearTimeout(settleTimeoutRef.current);
    settleTimeoutRef.current = null;
  }
}

function scheduleCommittedTransform(
  latestTransformRef: MutableRefObject<d3.ZoomTransform>,
  renderConfig: MapRenderConfig,
  animationFrameRef: MutableRefObject<number | null>,
  settleTimeoutRef: MutableRefObject<number | null>,
  setCommittedTransform: Dispatch<SetStateAction<d3.ZoomTransform>>,
  setIsInteracting: Dispatch<SetStateAction<boolean>>,
) {
  if (renderConfig.detailCommitMode === "animation-frame" && animationFrameRef.current === null) {
    animationFrameRef.current = window.requestAnimationFrame(() => {
      animationFrameRef.current = null;
      setCommittedTransform(latestTransformRef.current);
    });
  }

  clearSettleTimeout(settleTimeoutRef);
  settleTimeoutRef.current = window.setTimeout(() => {
    settleTimeoutRef.current = null;
    setCommittedTransform(latestTransformRef.current);
    setIsInteracting(false);
  }, renderConfig.interactionSettleMs);
}

function flushCommittedTransform(
  transform: d3.ZoomTransform,
  animationFrameRef: MutableRefObject<number | null>,
  settleTimeoutRef: MutableRefObject<number | null>,
  renderConfig: MapRenderConfig,
  setCommittedTransform: Dispatch<SetStateAction<d3.ZoomTransform>>,
  setIsInteracting: Dispatch<SetStateAction<boolean>>,
) {
  if (animationFrameRef.current !== null) {
    window.cancelAnimationFrame(animationFrameRef.current);
    animationFrameRef.current = null;
  }
  clearSettleTimeout(settleTimeoutRef);

  setCommittedTransform(transform);
  if (renderConfig.interactionSettleMs <= 0) {
    setIsInteracting(false);
    return;
  }
  settleTimeoutRef.current = window.setTimeout(() => {
    settleTimeoutRef.current = null;
    setIsInteracting(false);
  }, renderConfig.interactionSettleMs);
}

function baseSceneTransform(viewport: ViewportSize): string {
  const scale = Math.min(viewport.width, viewport.height);
  const offsetX = (viewport.width - scale) / 2;
  const offsetY = (viewport.height - scale) / 2;
  return `translate(${offsetX}, ${offsetY + scale}) scale(${scale}, ${-scale})`;
}

function fitZoneTransform(zone: ZoneRecord, viewport: ViewportSize): d3.ZoomTransform {
  return fitBBoxTransform(zone.bbox, viewport);
}

function fitBBoxTransform(
  bbox: [number, number, number, number],
  viewport: ViewportSize,
): d3.ZoomTransform {
  const [minX, minY, maxX, maxY] = projectBBox(bbox, viewport);
  const bboxWidth = Math.max(maxX - minX, 1);
  const bboxHeight = Math.max(maxY - minY, 1);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const fitScale = Math.min(
    (viewport.width - PADDING * 2) / bboxWidth,
    (viewport.height - PADDING * 2) / bboxHeight,
  );
  return d3.zoomIdentity
    .translate(viewport.width / 2 - fitScale * cx, viewport.height / 2 - fitScale * cy)
    .scale(fitScale);
}

function projectBBox(bbox: [number, number, number, number], viewport: ViewportSize) {
  const scale = Math.min(viewport.width, viewport.height);
  const offsetX = (viewport.width - scale) / 2;
  const offsetY = (viewport.height - scale) / 2;
  return [
    offsetX + bbox[0] * scale,
    offsetY + (1 - bbox[3]) * scale,
    offsetX + bbox[2] * scale,
    offsetY + (1 - bbox[1]) * scale,
  ] as const;
}

function focusZone(
  zoneId: number,
  bundle: FrontendBundle,
  viewport: ViewportSize,
  svgRef: RefObject<SVGSVGElement>,
  zoomRef: RefObject<d3.ZoomBehavior<SVGSVGElement, unknown> | null>,
  setFocusedZoneId: Dispatch<SetStateAction<number | null>>,
) {
  const zone = bundle.zones.get(zoneId);
  if (
    zone === undefined ||
    svgRef.current === null ||
    zoomRef.current === null ||
    viewport.width <= 0 ||
    viewport.height <= 0
  ) {
    return;
  }

  setFocusedZoneId(zoneId);
  d3.select(svgRef.current)
    .transition()
    .duration(850)
    .ease(d3.easeCubicInOut)
    .call(zoomRef.current.transform, fitZoneTransform(zone, viewport));
}

function zoneClassName(
  zone: ZoneRecord,
  hoveredZoneId: number | null,
  focusedZoneId: number | null,
  isInteracting: boolean,
  renderConfig: MapRenderConfig,
): string {
  const classes = ["region", animationClassForZone(zone.id)];
  if (hoveredZoneId === zone.id) {
    classes.push("is-hovered");
  }
  if (focusedZoneId === zone.id) {
    classes.push("is-focused");
  }
  if (isInteracting && renderConfig.disableEffectsWhileInteracting) {
    classes.push("is-interacting");
  }
  return classes.join(" ");
}

function borderClassName(
  border: BorderRecord,
  hoveredZoneId: number | null,
  focusedZoneId: number | null,
  isInteracting: boolean,
  renderConfig: MapRenderConfig,
): string {
  const classes = ["region-border"];
  if (hoveredZoneId !== null && border.zoneIds.includes(hoveredZoneId)) {
    classes.push("is-hovered");
  }
  if (focusedZoneId !== null && border.zoneIds.includes(focusedZoneId)) {
    classes.push("is-focused");
  }
  if (isInteracting && renderConfig.disableEffectsWhileInteracting) {
    classes.push("is-interacting");
  }
  return classes.join(" ");
}

function activeOutlineClassName(
  zone: ZoneRecord,
  hoveredZoneId: number | null,
  focusedZoneId: number | null,
  isInteracting: boolean,
  renderConfig: MapRenderConfig,
): string {
  const classes = ["active-outline"];
  if (hoveredZoneId === zone.id) {
    classes.push("is-hovered");
  } else if (focusedZoneId === zone.id) {
    classes.push("is-focused");
  }
  if (isInteracting && renderConfig.disableEffectsWhileInteracting) {
    classes.push("is-interacting");
  }
  return classes.join(" ");
}

function zoneColor(zoneId: number): string {
  const hue = (zoneId * 47) % 360;
  return d3.hsl(hue, 0.48, 0.55).formatHex();
}

function formatZoneName(name: string): string {
  return name.replace(/_/g, " ");
}

function combinedBBox(zones: ZoneRecord[]): [number, number, number, number] | null {
  if (zones.length === 0) {
    return null;
  }

  let [minX, minY, maxX, maxY] = zones[0].bbox;
  for (const zone of zones.slice(1)) {
    minX = Math.min(minX, zone.bbox[0]);
    minY = Math.min(minY, zone.bbox[1]);
    maxX = Math.max(maxX, zone.bbox[2]);
    maxY = Math.max(maxY, zone.bbox[3]);
  }
  return [minX, minY, maxX, maxY];
}

function resolveVisibleZones(
  bundle: FrontendBundle,
  currentScale: number,
  viewport: ViewportSize,
): ZoneRecord[] {
  const entryDepth = minVisibleDepth(bundle);
  const entryZones = bundle.levels.get(entryDepth) ?? [];
  const visible: ZoneRecord[] = [];

  for (const zoneId of entryZones) {
    const zone = bundle.zones.get(zoneId);
    if (zone !== undefined) {
      visible.push(...resolveVisibleBranch(bundle, zone, currentScale, viewport));
    }
  }

  return visible;
}

function resolveVisibleBranch(
  bundle: FrontendBundle,
  zone: ZoneRecord,
  currentScale: number,
  viewport: ViewportSize,
): ZoneRecord[] {
  if (zone.childIds.length === 0) {
    return [zone];
  }

  const revealScale = revealScaleForZone(zone, viewport);
  if (currentScale < revealScale) {
    return [zone];
  }

  const visibleChildren = zone.childIds.flatMap((childId) => {
    const child = bundle.zones.get(childId);
    return child === undefined ? [] : resolveVisibleBranch(bundle, child, currentScale, viewport);
  });

  return visibleChildren.length > 0 ? visibleChildren : [zone];
}

function revealScaleForZone(zone: ZoneRecord, viewport: ViewportSize): number {
  const [minX, minY, maxX, maxY] = projectBBox(zone.bbox, viewport);
  const bboxWidth = Math.max(maxX - minX, 1);
  const bboxHeight = Math.max(maxY - minY, 1);
  return Math.min(
    (viewport.width - PADDING * 2) / bboxWidth,
    (viewport.height - PADDING * 2) / bboxHeight,
  );
}

function hitTestVisibleZone(
  event: MouseEvent,
  visibleZones: ZoneRecord[],
  regionElements: Map<number, SVGPathElement>,
): number | null {
  for (const zone of [...visibleZones].reverse()) {
    const element = regionElements.get(zone.id);
    if (element === undefined) {
      continue;
    }
    const inverse = element.getScreenCTM()?.inverse();
    if (inverse === undefined || inverse === null) {
      continue;
    }
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(inverse);
    if (element.isPointInFill(point) || element.isPointInStroke(point)) {
      return zone.id;
    }
  }
  return null;
}

function minVisibleDepth(bundle: FrontendBundle): number {
  return bundle.maxDepth >= 1 ? 1 : 0;
}

function firstZoneAtDepth(bundle: FrontendBundle, depth: number): number | null {
  const zoneIds = bundle.levels.get(depth);
  return zoneIds !== undefined && zoneIds.length > 0 ? zoneIds[0] : null;
}
