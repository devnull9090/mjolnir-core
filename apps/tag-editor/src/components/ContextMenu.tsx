import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * The app's right-click menu: one host mounted once, surfaces call
 * [showContextMenu] from an `onContextMenu` handler with the items they can
 * offer. One menu at a time by construction; a second call replaces the first.
 */
export type MenuItem =
  | {
      label: string;
      action: () => void;
      disabled?: boolean;
      /** Red, for the destructive entry. */
      danger?: boolean;
      title?: string;
    }
  | "separator";

type MenuRequest = { items: MenuItem[]; x: number; y: number };

let openMenu: ((req: MenuRequest) => void) | null = null;

/**
 * Open the menu at the cursor. Suppresses the native menu and stops the event,
 * so nested surfaces (a field row inside a section) never both fire. Callers
 * that want the native menu for a target (a text box) simply return before
 * calling this.
 */
export function showContextMenu(
  e: { clientX: number; clientY: number; preventDefault(): void; stopPropagation(): void },
  items: MenuItem[],
): void {
  e.preventDefault();
  e.stopPropagation();
  openMenu?.({ items, x: e.clientX, y: e.clientY });
}

export function ContextMenuHost() {
  const [menu, setMenu] = useState<MenuRequest | null>(null);
  const [active, setActive] = useState(-1);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    openMenu = (req) => {
      setMenu(req);
      setActive(-1);
      setPos(null);
    };
    return () => {
      openMenu = null;
    };
  }, []);

  // Place after the menu has a size to measure: clamped to the right edge,
  // flipped above the cursor when the bottom leaves no room.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!menu || !el) return;
    const margin = 8;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const left = Math.min(Math.max(margin, menu.x), window.innerWidth - w - margin);
    let top = menu.y;
    if (top + h > window.innerHeight - margin) top = Math.max(margin, menu.y - h);
    setPos({ left, top });
  }, [menu]);

  // Focus only once visible: a visibility-hidden element refuses focus, and
  // without it the arrow keys would land wherever the right-click left them.
  useLayoutEffect(() => {
    if (pos) ref.current?.focus();
  }, [pos]);

  useEffect(() => {
    if (!menu) return;
    const outside = (e: Event) =>
      ref.current && !ref.current.contains(e.target as Node) && setMenu(null);
    const blur = () => setMenu(null);
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(null);
    };
    window.addEventListener("pointerdown", outside);
    // Capture phase: the scrolling pane swallows the bubble, and a menu
    // floating over content that just moved is anchored to nothing.
    window.addEventListener("scroll", outside, true);
    window.addEventListener("blur", blur);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("pointerdown", outside);
      window.removeEventListener("scroll", outside, true);
      window.removeEventListener("blur", blur);
      window.removeEventListener("keydown", key);
    };
  }, [menu]);

  if (!menu) return null;

  const enabled = menu.items
    .map((it, i) => (it !== "separator" && !it.disabled ? i : -1))
    .filter((i) => i >= 0);

  const move = (dir: 1 | -1) => {
    if (enabled.length === 0) return;
    const at = enabled.indexOf(active);
    const next =
      at < 0
        ? dir === 1
          ? enabled[0]
          : enabled[enabled.length - 1]
        : enabled[(at + dir + enabled.length) % enabled.length];
    setActive(next);
  };

  const run = (item: MenuItem) => {
    if (item === "separator" || item.disabled) return;
    setMenu(null);
    item.action();
  };

  return createPortal(
    <div
      ref={ref}
      role="menu"
      tabIndex={-1}
      className="fixed z-50 min-w-44 border border-border-subtle bg-surface-card py-1 shadow-2xl outline-none"
      style={{
        left: pos?.left ?? menu.x,
        top: pos?.top ?? menu.y,
        visibility: pos ? "visible" : "hidden",
      }}
      onContextMenu={(e) => e.preventDefault()}
      onKeyDown={(e) => {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          move(1);
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          move(-1);
        } else if (e.key === "Home") {
          e.preventDefault();
          if (enabled.length > 0) setActive(enabled[0]);
        } else if (e.key === "End") {
          e.preventDefault();
          if (enabled.length > 0) setActive(enabled[enabled.length - 1]);
        } else if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          if (active >= 0) run(menu.items[active]);
        }
      }}
    >
      {menu.items.map((item, i) =>
        item === "separator" ? (
          <div key={i} className="my-1 border-t border-border-subtle" />
        ) : (
          <button
            key={i}
            type="button"
            role="menuitem"
            disabled={item.disabled}
            title={item.title}
            className={`block w-full px-3 py-1 text-left text-xs ${
              item.disabled
                ? "text-text-dim opacity-40"
                : `${i === active ? "bg-surface-hover" : "hover:bg-surface-hover"} ${
                    item.danger
                      ? "text-accent-red"
                      : i === active
                        ? "text-text-primary"
                        : "text-text-secondary hover:text-text-primary"
                  }`
            }`}
            onPointerMove={() => setActive(i)}
            onClick={() => run(item)}
          >
            {item.label}
          </button>
        ),
      )}
    </div>,
    document.body,
  );
}
