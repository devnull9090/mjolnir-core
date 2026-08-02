/**
 * Report a mod to the moderators.
 *
 * Worth having on both surfaces for the same reason: the person best placed
 * to notice that a mod is malware, stolen or simply broken is whoever just
 * installed it, and that is more often the launcher than the website.
 */
import { useState } from "react";

import type { ReportReason, ReportSubject } from "../types";
import { useHub } from "./context";
import { AlertIcon } from "./icons";
import { ActionButton, ErrorNote } from "./primitives";

const REASONS: { key: ReportReason; label: string }[] = [
  { key: "malware", label: "Malicious or unsafe" },
  { key: "stolen", label: "Stolen work" },
  { key: "broken", label: "Broken or crashes the game" },
  { key: "nsfw", label: "Unmarked adult content" },
  { key: "spam", label: "Spam" },
  { key: "other", label: "Something else" },
];

export function ReportButton({
  subjectType = "mod",
  subjectId,
  label = "Report",
}: {
  subjectType?: ReportSubject;
  subjectId: string;
  label?: string;
}) {
  const { client, user, signIn } = useHub();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ReportReason>("broken");
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (done) {
    return (
      <span className="text-xs text-[var(--mj-text-dim)]">
        Reported — thank you. A moderator will look.
      </span>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => (user ? setOpen(true) : signIn())}
        className="inline-flex items-center gap-1 text-xs text-[var(--mj-text-dim)] hover:text-[var(--mj-red)] cursor-pointer"
        title={user ? undefined : "Sign in to report"}
      >
        <AlertIcon className="w-3.5 h-3.5" />
        {label}
      </button>
    );
  }

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await client.reportContent(subjectType, subjectId, reason, detail.trim());
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-[var(--mj-border)] p-3 space-y-2 max-w-md">
      <p className="text-xs font-semibold text-[var(--mj-text)]">What is wrong with this?</p>
      <select
        value={reason}
        onChange={(e) => setReason(e.target.value as ReportReason)}
        className="w-full px-2 py-1.5 text-sm rounded-lg bg-[var(--mj-bg)] border border-[var(--mj-border)] text-[var(--mj-text)] cursor-pointer"
        aria-label="Reason"
      >
        {REASONS.map((r) => (
          <option key={r.key} value={r.key}>
            {r.label}
          </option>
        ))}
      </select>
      <textarea
        value={detail}
        onChange={(e) => setDetail(e.target.value)}
        rows={3}
        maxLength={2000}
        placeholder="Anything that helps a moderator check quickly — what you saw, and when."
        className="w-full px-2 py-1.5 text-sm rounded-lg bg-[var(--mj-bg)] border border-[var(--mj-border)] text-[var(--mj-text)] placeholder:text-[var(--mj-text-dim)] focus:border-[var(--mj-gold)]/60 focus:outline-none"
      />
      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="flex gap-2">
        <ActionButton size="sm" tone="danger" onClick={() => void submit()} disabled={busy}>
          Send report
        </ActionButton>
        <ActionButton size="sm" tone="neutral" onClick={() => setOpen(false)}>
          Cancel
        </ActionButton>
      </div>
    </div>
  );
}
