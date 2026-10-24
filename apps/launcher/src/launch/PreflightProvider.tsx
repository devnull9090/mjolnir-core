/**
 * The checks every launch runs first, as a dialog over the launcher.
 *
 *   checking → (nothing found) → launch
 *            → review: updates, damaged installs, unsupported mods
 *                → Update and launch / Launch without updating / Cancel
 *            → applying, one step at a time → launch (or the failures)
 *
 * Offline is not a reason to stay home: a source that cannot be reached is
 * said, and Launch still works. The game's own out-of-date prompt starts the
 * same run in update mode (`mjolnir://update`), which first waits for the
 * game to close, since an update cannot replace files the game holds open.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ActionButton, ErrorNote, Spinner } from "@mjolnir/hub-kit";

import {
  PreflightContext,
  formatSize,
  repairStep,
  repairsNotCovered,
  setAsideStep,
  updateStep,
  type PreflightRequest,
  type Problem,
  type Step,
  type UpdateCheck,
} from "./preflight";

type StepStatus = "pending" | "running" | "done" | "failed";

type Phase =
  | { kind: "waiting-game" }
  | { kind: "checking" }
  | { kind: "review"; check: UpdateCheck; problems: Problem[] }
  | { kind: "applying"; steps: Step[]; status: Record<string, StepStatus>; errors: Record<string, string> }
  | { kind: "launching" }
  | { kind: "error"; message: string };

interface Pending {
  request: PreflightRequest;
  resolve: (launched: boolean) => void;
  reject: (e: unknown) => void;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function PreflightProvider({
  children,
  onApplied,
}: {
  children: ReactNode;
  /** After an apply run installed something: refresh what the screens show. */
  onApplied: () => void;
}) {
  const [phase, setPhase] = useState<Phase | null>(null);
  const [setAside, setSetAside] = useState(true);
  const pending = useRef<Pending | null>(null);
  // Read through a ref: the parent passes a fresh callback every render, and
  // `run` should stay the same function for its callers' effects.
  const appliedRef = useRef(onApplied);
  appliedRef.current = onApplied;
  // Bumped by Cancel, so a run still awaiting a check stops where it is.
  const generation = useRef(0);

  const finish = useCallback((launched: boolean) => {
    pending.current?.resolve(launched);
    pending.current = null;
    setPhase(null);
  }, []);

  const launch = useCallback(async () => {
    const p = pending.current;
    if (!p) return;
    setPhase({ kind: "launching" });
    pending.current = null;
    try {
      await p.request.launch();
      p.resolve(true);
      setPhase(null);
    } catch (e) {
      // The caller shows its own error (a join's "not ready"); the dialog
      // says it too in case the caller is the Launch button.
      p.reject(e);
      setPhase({ kind: "error", message: String(e) });
    }
  }, []);

  const apply = useCallback(
    async (steps: Step[]) => {
      if (steps.length === 0) return launch();
      const status: Record<string, StepStatus> = Object.fromEntries(steps.map((s) => [s.key, "pending"]));
      const errors: Record<string, string> = {};
      const show = () => setPhase({ kind: "applying", steps, status: { ...status }, errors: { ...errors } });
      show();
      let installed = false;
      // One at a time: they write to the same game folder.
      for (const step of steps) {
        status[step.key] = "running";
        show();
        try {
          await step.run();
          status[step.key] = "done";
          if (step.key !== "set-aside") installed = true;
        } catch (e) {
          status[step.key] = "failed";
          errors[step.key] = String(e);
        }
        show();
      }
      if (installed) appliedRef.current();
      if (Object.keys(errors).length === 0) return launch();
    },
    [launch],
  );

  const start = useCallback(
    async (request: PreflightRequest) => {
      const gen = ++generation.current;
      const live = () => gen === generation.current;
      setSetAside(true);
      if (request.update) {
        setPhase({ kind: "waiting-game" });
        while (live() && (await invoke<boolean>("game_is_running").catch(() => false))) {
          await sleep(2000);
        }
      } else if (await invoke<boolean>("game_is_running").catch(() => false)) {
        // Already running: Launch only brings it forward, and nothing
        // could be updated or moved under it anyway.
        return launch();
      }
      if (!live()) return;
      setPhase({ kind: "checking" });
      // Mods a previous session moved aside come back first, so the check
      // sees them and nothing moves them back under the game about to start.
      await invoke("unsupported_restore").catch(() => undefined);
      const [check, problems] = await Promise.all([
        invoke<UpdateCheck>("preflight_check").catch(
          (e): UpdateCheck => ({ checked_at: 0, items: [], unreachable: [String(e)], unsupported: [] }),
        ),
        invoke<Problem[]>("preflight_verify").catch((): Problem[] => []),
      ]);
      if (!live()) return;
      const repairs = repairsNotCovered(problems, check.items);
      const found = check.items.length + repairs.length + check.unsupported.length;
      if (found === 0) return launch();
      // The player already said "update" in game; only mods of theirs to
      // move need asking about.
      if (request.update && check.unsupported.length === 0) {
        return apply([...check.items.map(updateStep), ...repairs.map(repairStep)]);
      }
      setPhase({ kind: "review", check, problems: repairs });
    },
    [launch, apply],
  );

  const run = useCallback(
    (request: PreflightRequest) =>
      new Promise<boolean>((resolve, reject) => {
        // A second request (a click while one runs) replaces the first,
        // which counts as cancelled.
        pending.current?.resolve(false);
        pending.current = { request, resolve, reject };
        void start(request);
      }),
    [start],
  );

  const api = useMemo(() => ({ run }), [run]);

  const cancel = () => {
    generation.current++;
    finish(false);
  };

  // Escape closes the dialog when nothing is being written.
  useEffect(() => {
    if (!phase || phase.kind === "applying" || phase.kind === "launching") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") cancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <PreflightContext.Provider value={api}>
      {children}
      {phase && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-6"
          role="dialog"
          aria-modal="true"
          aria-label="Before you play"
        >
          <div className="w-full max-w-lg max-h-full overflow-y-auto rounded-xl border border-border-subtle bg-surface-secondary p-6 space-y-4">
            <Body
              phase={phase}
              setAside={setAside}
              onSetAside={setSetAside}
              onCancel={cancel}
              onLaunch={(update) => {
                if (phase.kind !== "review") return;
                const { check, problems } = phase;
                const steps = [
                  ...(update ? [...check.items.map(updateStep), ...problems.map(repairStep)] : []),
                  ...(setAside && check.unsupported.length > 0 ? [setAsideStep(check.unsupported)] : []),
                ];
                void apply(steps);
              }}
              onLaunchAnyway={() => void launch()}
            />
          </div>
        </div>
      )}
    </PreflightContext.Provider>
  );
}

function Body({
  phase,
  setAside,
  onSetAside,
  onCancel,
  onLaunch,
  onLaunchAnyway,
}: {
  phase: Phase;
  setAside: boolean;
  onSetAside: (v: boolean) => void;
  onCancel: () => void;
  onLaunch: (update: boolean) => void;
  onLaunchAnyway: () => void;
}) {
  switch (phase.kind) {
    case "waiting-game":
      return (
        <>
          <h2 className="text-lg font-bold">Updating MJOLNIR</h2>
          <p className="flex items-center gap-2 text-sm text-text-secondary">
            <Spinner className="w-4 h-4" />
            Waiting for the game to close. Updates start as soon as it has, and the game starts again
            after them.
          </p>
          <ActionButton tone="neutral" size="sm" onClick={onCancel}>
            Cancel
          </ActionButton>
        </>
      );
    case "checking":
      return (
        <>
          <h2 className="text-lg font-bold">Getting ready</h2>
          <p className="flex items-center gap-2 text-sm text-text-secondary">
            <Spinner className="w-4 h-4" />
            Checking for updates, checking your installed files, and looking for mods MJOLNIR does
            not support…
          </p>
          <ActionButton tone="neutral" size="sm" onClick={onCancel}>
            Cancel
          </ActionButton>
        </>
      );
    case "launching":
      return (
        <p className="flex items-center gap-2 text-sm text-text-secondary">
          <Spinner className="w-4 h-4" /> Starting the game…
        </p>
      );
    case "error":
      return (
        <>
          <h2 className="text-lg font-bold">The game did not start</h2>
          <ErrorNote>{phase.message}</ErrorNote>
          <ActionButton tone="neutral" size="sm" onClick={onCancel}>
            Close
          </ActionButton>
        </>
      );
    case "applying": {
      const failed = phase.steps.filter((s) => phase.status[s.key] === "failed");
      const done = phase.steps.every((s) => phase.status[s.key] === "done" || phase.status[s.key] === "failed");
      return (
        <>
          <h2 className="text-lg font-bold">{done ? "Some steps failed" : "Updating"}</h2>
          <ul className="space-y-1.5 text-sm">
            {phase.steps.map((s) => (
              <li key={s.key} className="flex items-start gap-2">
                <span className="w-4 shrink-0 pt-0.5">
                  {phase.status[s.key] === "running" ? (
                    <Spinner className="w-3.5 h-3.5" />
                  ) : phase.status[s.key] === "done" ? (
                    <span className="text-accent-green">✓</span>
                  ) : phase.status[s.key] === "failed" ? (
                    <span className="text-red-400">✕</span>
                  ) : (
                    <span className="text-text-secondary">·</span>
                  )}
                </span>
                <span className="flex-1">
                  {s.label}
                  {phase.errors[s.key] && (
                    <span className="block text-xs text-red-400/90 break-words">{phase.errors[s.key]}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
          {done && failed.length > 0 && (
            <div className="flex gap-2">
              <ActionButton onClick={onLaunchAnyway}>Launch anyway</ActionButton>
              <ActionButton tone="neutral" onClick={onCancel}>
                Close
              </ActionButton>
            </div>
          )}
        </>
      );
    }
    case "review": {
      const { check, problems } = phase;
      const fixes = check.items.length + problems.length;
      return (
        <>
          <div>
            <h2 className="text-lg font-bold">Before you play</h2>
            <p className="text-sm text-text-secondary mt-1">
              Multiplayer games need everyone on the same MJOLNIR versions and the same game files.
            </p>
          </div>

          {check.items.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold mb-1">
                {check.items.length} update{check.items.length === 1 ? "" : "s"}
              </h3>
              <ul className="text-sm text-text-secondary space-y-0.5">
                {check.items.map((o) => (
                  <li key={`${o.kind}:${o.id}`}>
                    {o.name}{" "}
                    <span className="font-mono text-xs">
                      {o.repair ? `v${o.latest} again (files missing)` : `${o.installed ?? "?"} → ${o.latest}`}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {problems.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold mb-1">Damaged installs</h3>
              <ul className="text-sm text-text-secondary space-y-0.5">
                {problems.map((p) => (
                  <li key={`${p.kind}:${p.id}`}>
                    {p.name}: <span className="text-xs">{p.detail}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {check.unsupported.length > 0 && (
            <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 space-y-2">
              <h3 className="text-sm font-semibold text-amber-400">
                {check.unsupported.length} mod{check.unsupported.length === 1 ? "" : "s"} MJOLNIR did not
                install
              </h3>
              <p className="text-xs text-text-secondary">
                Mods from elsewhere change the game for you alone, which can stop a multiplayer game
                from starting or desync it for the whole fireteam.
              </p>
              <ul className="text-xs text-text-secondary space-y-0.5 max-h-32 overflow-y-auto">
                {check.unsupported.map((m) => (
                  <li key={m.files[0]} title={m.files.join("\n")}>
                    <span className="font-mono">{m.name}</span>{" "}
                    ({m.kind === "pak" ? "pak" : "UE4SS mod"}, {formatSize(m.bytes)})
                  </li>
                ))}
              </ul>
              <label className="flex items-start gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={setAside}
                  onChange={(e) => onSetAside(e.target.checked)}
                />
                <span>
                  Move them aside while the game runs. Nothing is deleted: they go to
                  MJOLNIR-set-aside in the game folder and come back when the game closes.
                </span>
              </label>
            </section>
          )}

          {check.unreachable.length > 0 && (
            <p className="text-xs text-amber-400/90">
              Could not check {check.unreachable.join("; ")}.
            </p>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            {fixes > 0 ? (
              <>
                <ActionButton onClick={() => onLaunch(true)}>Update and launch</ActionButton>
                <ActionButton tone="neutral" onClick={() => onLaunch(false)}>
                  Launch without updating
                </ActionButton>
              </>
            ) : (
              <ActionButton onClick={() => onLaunch(false)}>Launch</ActionButton>
            )}
            <ActionButton tone="neutral" onClick={onCancel}>
              Cancel
            </ActionButton>
          </div>
        </>
      );
    }
  }
}
