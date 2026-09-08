import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

/**
 * The app's one floating surface: a fixed-position card anchored to a rect,
 * flipped above the anchor when the viewport leaves no room below, clamped to
 * the viewport edges. Dismissal is the caller's affair — Escape and any
 * pointerdown outside the card call `onClose`, hover lifetimes run on the
 * caller's timers through `onHoverChange`.
 *
 * An anchor that should survive its own clicks (a chip that toggles the
 * popover) must stopPropagation on pointerdown, or the outside-click close
 * fires first and the click reopens what it just dismissed.
 */
export function Popover({
  anchor,
  onClose,
  onHoverChange,
  children,
}: {
  anchor: DOMRect;
  onClose: () => void;
  onHoverChange?: (over: boolean) => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  // Position after the card has a size to measure; re-place when the content
  // changes shape (a thumbnail arriving, a player mounting).
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const margin = 8;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const left = Math.min(Math.max(margin, anchor.left), window.innerWidth - w - margin);
    let top = anchor.bottom + 6;
    if (top + h > window.innerHeight - margin) {
      top = Math.max(margin, anchor.top - h - 6);
    }
    setPos({ left, top });
  }, [anchor, children]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const down = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", key);
    window.addEventListener("pointerdown", down);
    return () => {
      window.removeEventListener("keydown", key);
      window.removeEventListener("pointerdown", down);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="fixed z-50 border border-border-subtle bg-surface-card shadow-2xl"
      style={{
        left: pos?.left ?? anchor.left,
        top: pos?.top ?? anchor.bottom + 6,
        visibility: pos ? "visible" : "hidden",
      }}
      onPointerEnter={() => onHoverChange?.(true)}
      onPointerLeave={() => onHoverChange?.(false)}
    >
      {children}
    </div>
  );
}
