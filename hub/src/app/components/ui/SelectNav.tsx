"use client";

import { ChevronDown } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId } from "react";

/**
 * A filter with too many choices for chips, as a native `<select>`: the
 * platform picker on a phone, type-to-find on a desktop. Each option is a
 * URL; choosing one navigates. Without JavaScript it is a GET form with a
 * Go button, so the filter never depends on hydration.
 */
export function SelectNav({
  label,
  name,
  value,
  options,
  action,
  hidden = {},
}: {
  label: string;
  /** The query parameter the choice sets. */
  name: string;
  value: string;
  options: { value: string; label: string; href: string }[];
  /** The page the no-script form submits to. */
  action: string;
  /** The other filters, kept across a no-script submit. */
  hidden?: Record<string, string | undefined>;
}) {
  const router = useRouter();
  const id = useId();
  return (
    <form action={action} method="get" className="flex items-center gap-2">
      <label htmlFor={id} className="text-sm text-text-muted whitespace-nowrap">
        {label}
      </label>
      {Object.entries(hidden).map(([k, v]) => (v ? <input key={k} type="hidden" name={k} value={v} /> : null))}
      <div className="relative min-w-0 flex-1 lg:flex-none">
        <select
          id={id}
          name={name}
          value={value}
          onChange={(e) => {
            const opt = options.find((o) => o.value === e.target.value);
            if (opt) router.push(opt.href, { scroll: false });
          }}
          className="min-h-10 w-full appearance-none rounded-lg border border-border bg-surface-raised py-2 pl-3 pr-9 text-sm text-foreground hover:border-border-bright focus:border-gold/60 lg:w-56"
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <ChevronDown
          aria-hidden
          className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
        />
      </div>
      <noscript>
        <button type="submit" className="min-h-10 rounded-lg border border-border px-3 text-sm text-text-muted">
          Go
        </button>
      </noscript>
    </form>
  );
}
