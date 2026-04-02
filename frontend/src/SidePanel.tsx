import type { ReactNode } from "react";
import { useCallback, useState } from "react";
import type { PanelState, SidePanelConfig } from "./types";

interface SidePanelProps {
  config: SidePanelConfig;
  children?: ReactNode;
}

const STATE_CYCLE: PanelState[] = ["hidden", "half", "full"];

const TOGGLE_LABELS: Record<PanelState, string> = {
  hidden: "\u276f",
  half: "\u276f",
  full: "\u276e",
};

export function SidePanel({ config, children }: SidePanelProps) {
  const [internalState, setInternalState] = useState<PanelState>(
    config.defaultState ?? "hidden",
  );

  const isControlled = config.state !== undefined;
  const currentState = isControlled ? config.state! : internalState;

  const cycleState = useCallback(() => {
    const currentIndex = STATE_CYCLE.indexOf(currentState);
    const nextState = STATE_CYCLE[(currentIndex + 1) % STATE_CYCLE.length];
    if (!isControlled) {
      setInternalState(nextState);
    }
    config.onStateChange?.(nextState);
  }, [currentState, isControlled, config]);

  const position = config.position ?? "right";

  return (
    <div
      className={`side-panel side-panel--${currentState} side-panel--${position}`}
    >
      <button
        className="side-panel__toggle"
        type="button"
        onClick={cycleState}
        aria-label={currentState === "full" ? "Collapse panel" : "Expand panel"}
      >
        {position === "left"
          ? currentState === "full"
            ? "\u276e"
            : "\u276f"
          : TOGGLE_LABELS[currentState]}
      </button>
      <div className="side-panel__content">{children}</div>
    </div>
  );
}
