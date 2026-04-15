import type { PointerEvent as ReactPointerEvent, ReactNode } from "react";
import { useCallback, useRef, useState } from "react";
import type { PanelState, SidePanelConfig } from "./types";

interface SidePanelProps {
  config: SidePanelConfig;
  children?: ReactNode;
}

const MIN_PANEL_PX = 24;
const HIDDEN_SNAP_FRACTION = 0.12;
const FULL_SNAP_FRACTION = 0.82;

const STATE_CYCLE: PanelState[] = ["hidden", "half", "full"];

const CHEVRON_LEFT = "\u276e"; // ❮
const CHEVRON_RIGHT = "\u276f"; // ❯

/**
 * Returns the chevron glyph that hints at the direction the next cycle step
 * will move the panel. For a right-positioned panel, the panel grows from
 * the right edge toward the left; so while the panel is smaller than full,
 * the next step grows leftward (show ❮), and while it is full the next step
 * collapses rightward (show ❯). Left panels mirror.
 */
function toggleGlyph(state: PanelState, position: "left" | "right"): string {
  const cycleGrowsPanel = state !== "full";
  const growsLeftward = position === "right";
  const growDirection = growsLeftward ? CHEVRON_LEFT : CHEVRON_RIGHT;
  const collapseDirection = growsLeftward ? CHEVRON_RIGHT : CHEVRON_LEFT;
  return cycleGrowsPanel ? growDirection : collapseDirection;
}

export function SidePanel({ config, children }: SidePanelProps) {
  const [internalState, setInternalState] = useState<PanelState>(
    config.defaultState ?? "hidden",
  );
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [dragWidth, setDragWidth] = useState<number | null>(null);
  const dragActiveRef = useRef(false);

  const isControlled = config.state !== undefined;
  const currentState = isControlled ? config.state! : internalState;
  const position = config.position ?? "right";

  const applyState = useCallback(
    (nextState: PanelState) => {
      if (!isControlled) {
        setInternalState(nextState);
      }
      config.onStateChange?.(nextState);
    },
    [isControlled, config],
  );

  const cycleState = useCallback(() => {
    const currentIndex = STATE_CYCLE.indexOf(currentState);
    const nextState = STATE_CYCLE[(currentIndex + 1) % STATE_CYCLE.length];
    applyState(nextState);
  }, [currentState, applyState]);

  const computeDragWidth = useCallback(
    (clientX: number): number | null => {
      const panel = panelRef.current;
      const layout = panel?.parentElement;
      if (panel === null || panel === undefined || layout === null || layout === undefined) {
        return null;
      }
      const layoutRect = layout.getBoundingClientRect();
      const rawWidth =
        position === "right"
          ? layoutRect.right - clientX
          : clientX - layoutRect.left;
      const clamped = Math.max(0, Math.min(layoutRect.width, rawWidth));
      return clamped < MIN_PANEL_PX ? 0 : clamped;
    },
    [position],
  );

  const snapFromWidth = useCallback(
    (widthPx: number): PanelState => {
      const layout = panelRef.current?.parentElement;
      const layoutWidth = layout?.getBoundingClientRect().width ?? 0;
      if (layoutWidth <= 0) {
        return currentState;
      }
      const fraction = widthPx / layoutWidth;
      if (fraction < HIDDEN_SNAP_FRACTION) {
        return "hidden";
      }
      if (fraction > FULL_SNAP_FRACTION) {
        return "full";
      }
      return "half";
    },
    [currentState],
  );

  const handlePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      event.currentTarget.setPointerCapture(event.pointerId);
      dragActiveRef.current = true;
      const initial = computeDragWidth(event.clientX);
      if (initial !== null) {
        setDragWidth(initial);
      }
    },
    [computeDragWidth],
  );

  const handlePointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (!dragActiveRef.current) {
        return;
      }
      const nextWidth = computeDragWidth(event.clientX);
      if (nextWidth !== null) {
        setDragWidth(nextWidth);
      }
    },
    [computeDragWidth],
  );

  const handlePointerUp = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (!dragActiveRef.current) {
        return;
      }
      dragActiveRef.current = false;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      const finalWidth = computeDragWidth(event.clientX);
      setDragWidth(null);
      if (finalWidth === null) {
        return;
      }
      const nextState = snapFromWidth(finalWidth);
      if (nextState !== currentState) {
        applyState(nextState);
      }
    },
    [computeDragWidth, snapFromWidth, currentState, applyState],
  );

  const isDragging = dragWidth !== null;
  const panelStyle =
    isDragging && dragWidth !== null
      ? { width: `${dragWidth}px`, transition: "none" as const }
      : undefined;

  return (
    <div
      ref={panelRef}
      className={`side-panel side-panel--${currentState} side-panel--${position}${
        isDragging ? " side-panel--dragging" : ""
      }`}
      style={panelStyle}
    >
      <div
        className="side-panel__resize-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panel"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      />
      <button
        className="side-panel__toggle"
        type="button"
        onClick={cycleState}
        aria-label={currentState === "full" ? "Collapse panel" : "Expand panel"}
      >
        {toggleGlyph(currentState, position)}
      </button>
      <div className="side-panel__content">{children}</div>
    </div>
  );
}
