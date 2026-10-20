/**
 * Settings' list of recent crashes, each with a way to send it: for a crash
 * dismissed from the banner, one from before the launcher watched, or one
 * the MJOLNIR team asked about.
 */
import { useState } from "react";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { useHub } from "@mjolnir/hub-kit";
import {
  type Crash,
  crashKind,
  crashPlace,
  errorText,
  formatWhen,
  sendCrash,
  sendCrashDump,
  useCrashes,
  zippedDumpSize,
} from "../crash/crashes";

const button =
  "px-3 py-1.5 rounded-lg text-xs font-medium bg-surface-card border border-border-subtle text-text-secondary hover:text-text-primary hover:border-accent-blue/40 disabled:opacity-50 transition-all duration-150 cursor-pointer";

export default function CrashReports() {
  const { crashes } = useCrashes();

  return (
    <section className="mb-8">
      <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4 flex items-center gap-2">
        <svg className="w-4 h-4 text-mjolnir-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
        Crash Reports
      </h3>
      <p className="text-xs text-text-secondary mb-4">
        When the game crashes, the launcher offers to send a report so the MJOLNIR team can find the cause.
        Nothing is sent unless you choose to. Your PC's and Epic account's IDs and your Windows user name are
        removed first.
      </p>

      {crashes === null ? (
        <div className="flex items-center justify-center h-16">
          <div className="w-5 h-5 border-2 border-mjolnir-gold border-t-transparent rounded-full animate-spin" />
        </div>
      ) : crashes.length === 0 ? (
        <p className="text-xs text-text-secondary">No crashes found.</p>
      ) : (
        <div className="rounded-xl border border-border-subtle bg-surface-card overflow-hidden">
          {crashes.map((c, i) => (
            <CrashRow key={c.id} crash={c} last={i === crashes.length - 1} />
          ))}
        </div>
      )}
    </section>
  );
}

function CrashRow({ crash, last }: { crash: Crash; last: boolean }) {
  const { user, signIn } = useHub();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  let action;
  if (crash.dump_requested) {
    action = (
      <button disabled={busy} onClick={() => void run(() => sendCrashDump(crash.id))} className={button}>
        {busy ? "Uploading…" : `Send full dump (${zippedDumpSize(crash)})`}
      </button>
    );
  } else if (crash.status === "sent") {
    action = (
      <span className="text-xs text-accent-green font-medium">{crash.dump_sent ? "Sent with dump" : "Sent"}</span>
    );
  } else if (!user) {
    action = (
      <button onClick={signIn} className={button}>
        Sign in to send
      </button>
    );
  } else {
    action = (
      <button disabled={busy} onClick={() => void run(() => sendCrash(crash.id))} className={button}>
        {busy ? "Sending…" : "Send report"}
      </button>
    );
  }

  return (
    <div className={`px-4 py-3 ${last ? "" : "border-b border-border-subtle/50"}`}>
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="text-sm text-text-primary">
            {crashKind(crash)} <span className="text-text-secondary">· {formatWhen(crash.crashed_at)}</span>
          </div>
          <div className="text-xs text-text-secondary truncate" title={crash.fault}>
            {crashPlace(crash)}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => void revealItemInDir(crash.folder)}
            className="px-2 py-1.5 rounded-lg text-xs text-text-secondary hover:text-text-primary hover:bg-surface-hover transition-all cursor-pointer"
          >
            Files
          </button>
          {action}
        </div>
      </div>
      {error && <p className="text-xs text-accent-red font-medium mt-2">{error}</p>}
    </div>
  );
}
