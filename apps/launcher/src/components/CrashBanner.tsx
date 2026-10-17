/**
 * Asks about the game's newest crash: send a report, or not now. Nothing
 * leaves the machine without the click, and the full memory dump only after
 * a second one, when the hub asks for it (docs/crash_reports.md).
 *
 * One crash at a time, newest first; the rest wait in Settings.
 */
import { useState, type ReactNode } from "react";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { useHub } from "@mjolnir/hub-kit";
import {
  crashPlace,
  declineCrashDump,
  dismissCrash,
  errorText,
  isSignedOut,
  sendCrash,
  sendCrashDump,
  useCrashes,
  zippedDumpSize,
} from "../crash/crashes";

const primary =
  "px-3 py-1 rounded bg-mjolnir-gold text-surface-primary text-xs font-bold hover:brightness-110 disabled:opacity-50 transition-all cursor-pointer";
const quiet =
  "px-2 py-1 rounded text-xs text-text-secondary hover:text-text-primary hover:bg-surface-hover disabled:opacity-50 transition-all cursor-pointer";

export default function CrashBanner() {
  const { user, signIn } = useHub();
  const { crashes } = useCrashes();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsSignIn, setNeedsSignIn] = useState(false);
  const [details, setDetails] = useState(false);
  const [thanks, setThanks] = useState<string | null>(null);

  const crash = crashes?.find((c) => c.status === "new" || c.dump_requested) ?? null;

  const run = async (work: () => Promise<string | null>) => {
    setBusy(true);
    setError(null);
    try {
      const done = await work();
      if (done) setThanks(done);
      setNeedsSignIn(false);
      setDetails(false);
    } catch (e) {
      setNeedsSignIn(isSignedOut(e));
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  if (thanks) {
    return (
      <Bar
        actions={
          <button onClick={() => setThanks(null)} className={quiet}>
            Close
          </button>
        }
      >
        <span className="text-xs text-text-primary">{thanks}</span>
      </Bar>
    );
  }
  if (!crash) return null;

  const signInButton = (
    <button onClick={signIn} className={primary}>
      Sign in to send
    </button>
  );

  // The report went in, and the hub has too few dumps of this crash.
  if (crash.dump_requested) {
    return (
      <Bar
        actions={
          <>
            {needsSignIn ? (
              signInButton
            ) : (
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    await sendCrashDump(crash.id);
                    return "Thanks, the crash dump is in.";
                  })
                }
                className={primary}
              >
                {busy ? "Uploading…" : "Send full dump"}
              </button>
            )}
            <button
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await declineCrashDump(crash.id);
                  return null;
                })
              }
              className={quiet}
            >
              No thanks
            </button>
          </>
        }
      >
        <div className="flex flex-col gap-0.5">
          <span className="text-xs text-text-primary">
            Thanks, the report is in. This crash is new to us: would you also send the full crash dump (about{" "}
            {zippedDumpSize(crash)})?
          </span>
          <span className="text-[11px] text-text-secondary">
            It is a copy of the game's memory when it crashed, so it can hold things like your in-game name and
            what was on screen.
          </span>
          {error && <span className="text-[11px] text-accent-red font-medium">{error}</span>}
        </div>
      </Bar>
    );
  }

  return (
    <Bar
      actions={
        <>
          {!user || needsSignIn ? (
            signInButton
          ) : (
            <button
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const sent = await sendCrash(crash.id);
                  // When the hub wants the dump, this bar asks about it next.
                  return sent.dump_requested ? null : "Thanks, the crash report is in.";
                })
              }
              className={primary}
            >
              {busy ? "Sending…" : "Send report"}
            </button>
          )}
          <button onClick={() => setDetails((d) => !d)} className={quiet}>
            {details ? "Hide details" : "What's sent?"}
          </button>
          <button
            disabled={busy}
            onClick={() =>
              void run(async () => {
                await dismissCrash(crash.id);
                return null;
              })
            }
            className={quiet}
          >
            Not now
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-1 min-w-0">
        <span className="text-xs text-text-primary">
          The game crashed {crashPlace(crash)}. Send a crash report so we can find the cause?
        </span>
        {details && (
          <ul className="text-[11px] text-text-secondary space-y-0.5">
            <li>• Where it crashed, the game build, the map, and how long it had run</li>
            <li>• A trimmed crash dump: the threads and loaded modules, without the game's memory</li>
            {crash.log_saved && <li>• UE4SS.log from that session</li>}
            <li>• Your installed mods and their versions</li>
            <li>• Removed first: your PC's and Epic account's IDs, and your Windows user name in file paths</li>
            <li>
              <button
                onClick={() => void revealItemInDir(crash.folder)}
                className="underline hover:text-text-primary cursor-pointer"
              >
                Show the crash files
              </button>
            </li>
          </ul>
        )}
        {error && <span className="text-[11px] text-accent-red font-medium">{error}</span>}
      </div>
    </Bar>
  );
}

function Bar({ children, actions }: { children: ReactNode; actions: ReactNode }) {
  return (
    <div className="bg-mjolnir-gold/10 border-b border-mjolnir-gold/30 px-6 py-2.5 flex items-start justify-between gap-4">
      <div className="flex items-start gap-3 min-w-0">
        <span className="w-2 h-2 rounded-full bg-mjolnir-gold mt-1 shrink-0" />
        {children}
      </div>
      <div className="flex items-center gap-2 shrink-0">{actions}</div>
    </div>
  );
}
