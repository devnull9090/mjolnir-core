/**
 * The launch dialog's live checklist: every item the checks look at, filled
 * in as the backend reports it (`preflight-progress`, src-tauri/src/
 * preflight.rs), under one bar for the whole run. A long map list then reads
 * as progress, not as one spinner that takes forever.
 */
import { useEffect, useRef } from "react";
import { Spinner } from "@mjolnir/hub-kit";

import type { CheckStep } from "./preflight";

const GROUPS: { id: CheckStep["group"]; title: string }[] = [
  { id: "updates", title: "Updates" },
  { id: "files", title: "Installed files" },
  { id: "mods", title: "Other mods" },
];

const finished = (s: CheckStep) => s.state === "ok" || s.state === "warn" || s.state === "fail";

export function StateIcon({ state }: { state: CheckStep["state"] | "done" | "failed" }) {
  switch (state) {
    case "running":
      return <Spinner className="w-3.5 h-3.5" />;
    case "ok":
    case "done":
      return <span className="text-accent-green">✓</span>;
    case "warn":
      return <span className="text-amber-400">!</span>;
    case "fail":
    case "failed":
      return <span className="text-red-400">✕</span>;
    default:
      return <span className="text-text-secondary">·</span>;
  }
}

export function ProgressBar({ fraction }: { fraction: number }) {
  return (
    <div className="h-1.5 w-full rounded-full bg-surface-primary overflow-hidden">
      <div
        className="h-full bg-mjolnir-gold transition-[width] duration-200"
        style={{ width: `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%` }}
      />
    </div>
  );
}

export default function Checklist({ steps }: { steps: CheckStep[] }) {
  const done = steps.filter(finished).length;
  const running = steps.filter((s) => s.state === "running");
  // A long map list runs below the fold: keep the row being worked on in
  // view.
  const list = useRef<HTMLDivElement>(null);
  const current = running[running.length - 1]?.key;
  useEffect(() => {
    if (!current) return;
    const row = list.current?.querySelector(`[data-key="${CSS.escape(current)}"]`);
    row?.scrollIntoView({ block: "nearest" });
  }, [current]);
  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <ProgressBar fraction={steps.length ? done / steps.length : 0} />
        <p className="text-xs text-text-secondary">
          {steps.length === 0
            ? "Starting…"
            : `${done} of ${steps.length} checked${running.length > 0 ? ` · ${running.map((s) => s.label).join(", ")}` : ""}`}
        </p>
      </div>
      <div ref={list} className="max-h-72 overflow-y-auto pr-1 space-y-3">
        {GROUPS.map((g) => {
          const rows = steps.filter((s) => s.group === g.id);
          if (rows.length === 0) return null;
          return (
            <section key={g.id}>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-text-secondary mb-1">
                {g.title}{" "}
                <span className="font-normal normal-case">
                  {rows.filter(finished).length}/{rows.length}
                </span>
              </h3>
              <ul className="space-y-0.5 text-sm">
                {rows.map((s) => (
                  <li
                    key={s.key}
                    data-key={s.key}
                    className={`flex items-start gap-2 ${s.state === "pending" ? "text-text-secondary/60" : ""}`}
                  >
                    <span className="w-4 shrink-0 pt-0.5 text-center">
                      <StateIcon state={s.state} />
                    </span>
                    <span className={`flex-1 min-w-0 truncate ${s.parent ? "pl-3" : ""}`} title={s.label}>
                      {s.label}
                    </span>
                    {s.detail && (
                      <span
                        className={`shrink-0 max-w-[50%] truncate text-xs ${
                          s.state === "warn" ? "text-amber-400" : s.state === "fail" ? "text-red-400" : "text-text-secondary"
                        }`}
                        title={s.detail}
                      >
                        {s.detail}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
