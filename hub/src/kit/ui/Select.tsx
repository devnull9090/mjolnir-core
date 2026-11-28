/**
 * One custom dropdown for both the hub website and the desktop launcher.
 *
 * Replaces native `<select>` popups with an obsidian-and-gold WAI-ARIA listbox
 * styled solely against `--mj-*` theme variables. Supports keyboard navigation
 * (arrows, Home/End, Enter/Space, Escape, type-ahead), outside-click dismiss,
 * and an optional hidden input so standard HTML forms keep working.
 */
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { CheckIcon, ChevronDownIcon } from "./icons";

export interface SelectOption<T extends string = string> {
  value: T;
  label: string;
}

export function Select<T extends string = string>({
  id,
  name,
  value,
  onChange,
  options,
  placeholder = "Select…",
  ariaLabel,
  ariaLabelledBy,
  disabled = false,
  size = "md",
  align = "auto",
  className = "",
}: {
  id?: string;
  /** Emits a hidden `<input>` so enclosing HTML forms carry the chosen value. */
  name?: string;
  value: T;
  onChange: (value: T) => void;
  options: readonly SelectOption<T>[];
  placeholder?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  disabled?: boolean;
  size?: "sm" | "md";
  /** Which edge the floating menu pins to; `"auto"` flips right near the viewport edge. */
  align?: "auto" | "left" | "right";
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [menuAlign, setMenuAlign] = useState<"left" | "right">("left");
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const typeBuffer = useRef("");
  const typeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reactId = useId();
  const listId = `${reactId}-listbox`;

  const selectedIndex = options.findIndex((o) => o.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : null;

  const openMenu = (startIndex?: number) => {
    if (disabled || options.length === 0) return;
    if (align === "auto" && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      // Pin right when the trigger sits on the right half and has less room to its right.
      const roomRight = window.innerWidth - rect.left;
      setMenuAlign(roomRight < 260 && rect.right > 260 ? "right" : "left");
    } else {
      setMenuAlign(align === "right" ? "right" : "left");
    }
    setActiveIndex(startIndex ?? (selectedIndex >= 0 ? selectedIndex : 0));
    setOpen(true);
  };

  const closeMenu = (restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) buttonRef.current?.focus();
  };

  const commit = (opt: SelectOption<T>) => {
    if (opt.value !== value) onChange(opt.value);
    closeMenu(true);
  };

  // Close on click/tap outside the component.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  // Keep the highlighted option scrolled into view when navigating long lists.
  useEffect(() => {
    if (!open) return;
    const item = listRef.current?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
    item?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex]);

  useEffect(() => () => {
    if (typeTimer.current) clearTimeout(typeTimer.current);
  }, []);

  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled || options.length === 0) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!open) openMenu();
        else setActiveIndex((i) => (i + 1) % options.length);
        return;
      case "ArrowUp":
        e.preventDefault();
        if (!open) openMenu();
        else setActiveIndex((i) => (i - 1 + options.length) % options.length);
        return;
      case "Home":
        if (open) {
          e.preventDefault();
          setActiveIndex(0);
        }
        return;
      case "End":
        if (open) {
          e.preventDefault();
          setActiveIndex(options.length - 1);
        }
        return;
      case "Enter":
      case " ":
        e.preventDefault();
        if (!open) openMenu();
        else if (options[activeIndex]) commit(options[activeIndex]);
        return;
      case "Escape":
        if (open) {
          e.preventDefault();
          closeMenu(true);
        }
        return;
      case "Tab":
        if (open) setOpen(false);
        return;
    }

    // Type-ahead: jump to the first option starting with typed characters.
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (typeTimer.current) clearTimeout(typeTimer.current);
      typeBuffer.current = (typeBuffer.current + e.key).toLowerCase();
      typeTimer.current = setTimeout(() => {
        typeBuffer.current = "";
      }, 500);
      const hit = options.findIndex((o) => o.label.toLowerCase().startsWith(typeBuffer.current));
      if (hit >= 0) {
        if (open) setActiveIndex(hit);
        else onChange(options[hit].value);
      }
    }
  };

  const triggerSizing =
    size === "sm"
      ? "min-h-8 px-2.5 py-1 text-xs gap-2"
      : "min-h-10 px-3 py-2 text-sm gap-2.5";

  const optionSizing =
    size === "sm"
      ? "px-2.5 py-1.5 text-xs gap-2"
      : "px-3 py-2 text-sm gap-2.5";

  return (
    <div ref={rootRef} className={`relative inline-block ${className}`}>
      {name && <input type="hidden" name={name} value={value} />}
      <button
        ref={buttonRef}
        id={id}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open ? `${listId}-opt-${activeIndex}` : undefined}
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledBy}
        disabled={disabled}
        onClick={() => (open ? closeMenu() : openMenu())}
        onKeyDown={handleKeyDown}
        className={`flex w-full items-center justify-between rounded-lg border bg-[var(--mj-surface-raised)] text-left text-[var(--mj-text)] transition-all duration-150 cursor-pointer disabled:opacity-45 disabled:cursor-default ${triggerSizing} ${
          open
            ? "border-[var(--mj-gold)]/70 ring-1 ring-[var(--mj-gold)]/20"
            : "border-[var(--mj-border)] hover:border-[var(--mj-border-bright)]"
        }`}
      >
        <span className={`truncate ${selected ? "" : "text-[var(--mj-text-muted)]"}`}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDownIcon
          className={`shrink-0 transition-transform duration-150 ${
            size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4"
          } ${open ? "rotate-180 text-[var(--mj-gold)]" : "text-[var(--mj-text-muted)]"}`}
        />
      </button>

      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          aria-label={ariaLabel}
          aria-labelledby={ariaLabelledBy}
          className={`mj-dropdown-menu absolute top-full z-50 mt-1.5 min-w-full w-max max-w-[min(18rem,calc(100vw-2rem))] max-h-64 overflow-y-auto rounded-xl border border-[var(--mj-border-bright)] bg-[var(--mj-surface-raised)] p-1 shadow-[0_18px_44px_-12px_rgba(0,0,0,0.85)] ${
            menuAlign === "right" ? "right-0" : "left-0"
          }`}
        >
          {options.map((opt, idx) => {
            const isSelected = opt.value === value;
            const isActive = idx === activeIndex;
            return (
              <li
                key={opt.value}
                id={`${listId}-opt-${idx}`}
                data-index={idx}
                role="option"
                aria-selected={isSelected}
                onMouseEnter={() => setActiveIndex(idx)}
                onMouseDown={(e) => {
                  // Prevent blur before click completes.
                  e.preventDefault();
                }}
                onClick={() => commit(opt)}
                className={`relative flex items-center justify-between rounded-lg transition-colors duration-100 cursor-pointer select-none ${optionSizing} ${
                  isSelected
                    ? "bg-[var(--mj-gold)]/14 text-[var(--mj-gold)] font-semibold"
                    : isActive
                      ? "bg-[var(--mj-surface-hover)] text-[var(--mj-text)]"
                      : "text-[var(--mj-text-muted)] hover:text-[var(--mj-text)]"
                }`}
              >
                <span className="truncate">{opt.label}</span>
                {isSelected && (
                  <CheckIcon className="w-3.5 h-3.5 shrink-0 text-[var(--mj-gold)]" />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
