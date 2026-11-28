"use client";

import { useRouter } from "next/navigation";
import { useId } from "react";

import { Select } from "../HubKit";

/**
 * A filter with too many choices for chips, backed by the shared MJOLNIR
 * `<Select>` listbox. Each option maps to a URL; picking one navigates while
 * preserving the form for progressive enhancement.
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
  const labelId = `${id}-label`;

  return (
    <form action={action} method="get" className="flex items-center gap-2">
      <label id={labelId} htmlFor={id} className="text-sm text-text-muted whitespace-nowrap">
        {label}
      </label>
      {Object.entries(hidden).map(([k, v]) => (v ? <input key={k} type="hidden" name={k} value={v} /> : null))}
      <Select
        id={id}
        name={name}
        value={value}
        ariaLabelledBy={labelId}
        options={options}
        onChange={(next) => {
          const opt = options.find((o) => o.value === next);
          if (opt) router.push(opt.href, { scroll: false });
        }}
        className="min-w-0 flex-1 sm:min-w-48 lg:w-56 sm:flex-none"
      />
      <noscript>
        <button type="submit" className="min-h-10 rounded-lg border border-border px-3 text-sm text-text-muted">
          Go
        </button>
      </noscript>
    </form>
  );
}
