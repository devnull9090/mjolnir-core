"use client";

import { useState } from "react";
import { Check, Copy, Terminal } from "lucide-react";

/**
 * Code snippet box with a crisp one-click copy button and visual confirmation.
 */
export function CopyCommand({
  label,
  command,
}: {
  label?: string;
  command: string;
}) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    void navigator.clipboard.writeText(command).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };

  return (
    <div className="group rounded-xl border border-border bg-surface-card/90 overflow-hidden transition-colors hover:border-border-bright">
      {label && (
        <div className="flex items-center justify-between gap-2 border-b border-border/80 bg-background/40 px-3.5 py-2">
          <span className="inline-flex items-center gap-2 font-mono text-[11px] font-medium uppercase tracking-wider text-text-dim">
            <Terminal aria-hidden="true" className="size-3 text-gold" />
            {label}
          </span>
          <button
            type="button"
            onClick={copy}
            className="inline-flex items-center gap-1.5 rounded-md border border-border-bright bg-surface-raised px-2.5 py-1 text-[11px] font-medium text-text-muted transition-all hover:border-gold/45 hover:text-foreground cursor-pointer"
          >
            {copied ? (
              <>
                <Check aria-hidden="true" className="size-3 text-accent-green" />
                <span className="text-accent-green font-semibold">Copied</span>
              </>
            ) : (
              <>
                <Copy aria-hidden="true" className="size-3" />
                Copy
              </>
            )}
          </button>
        </div>
      )}
      <div className="relative flex items-start justify-between gap-2 p-3.5">
        <pre className="flex-1 overflow-x-auto text-sm font-mono leading-6 text-foreground">
          <code>{command}</code>
        </pre>
        {!label && (
          <button
            type="button"
            onClick={copy}
            aria-label="Copy command"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border-bright bg-surface-raised px-2.5 py-1 text-[11px] font-medium text-text-muted transition-all hover:border-gold/45 hover:text-foreground cursor-pointer"
          >
            {copied ? (
              <>
                <Check aria-hidden="true" className="size-3 text-accent-green" />
                <span className="text-accent-green font-semibold">Copied</span>
              </>
            ) : (
              <>
                <Copy aria-hidden="true" className="size-3" />
                Copy
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

const CLI_TABS = [
  {
    key: "windows",
    label: "Windows (Scoop)",
    command: `scoop bucket add mjolnir https://github.com/devnull9090/mjolnir-core\nscoop install mjolnir`,
  },
  {
    key: "unix",
    label: "macOS & Linux (Homebrew)",
    command: `brew tap devnull9090/core https://github.com/devnull9090/mjolnir-core\nbrew install mjolnir`,
  },
] as const;

/**
 * Interactive platform switcher for installing the standalone mjolnir CLI.
 */
export function CliInstallTabs() {
  const [tab, setTab] = useState<(typeof CLI_TABS)[number]["key"]>("windows");
  const current = CLI_TABS.find((t) => t.key === tab) ?? CLI_TABS[0];

  return (
    <div className="mt-4 space-y-2.5">
      <div role="tablist" aria-label="CLI installation platform" className="inline-flex rounded-lg border border-border bg-background/70 p-1">
        {CLI_TABS.map((t) => {
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(t.key)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-all cursor-pointer ${
                active
                  ? "bg-gold/15 text-gold shadow-sm"
                  : "text-text-muted hover:text-foreground"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      <div key={current.key} className="mj-tab-fade">
        <CopyCommand label={current.label} command={current.command} />
      </div>
    </div>
  );
}
