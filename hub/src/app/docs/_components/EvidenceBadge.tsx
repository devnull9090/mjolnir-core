export type EvidenceLevel = "Verified" | "Observed" | "Hypothesis" | "Unverified";

const styles: Record<EvidenceLevel, string> = {
  Verified: "border-accent-green/40 bg-accent-green/10 text-accent-green",
  Observed: "border-accent-blue/40 bg-accent-blue/10 text-accent-blue",
  Hypothesis: "border-gold/40 bg-gold/10 text-gold",
  Unverified: "border-border-bright bg-surface-raised text-text-muted",
};

export function EvidenceBadge({ level }: { level: EvidenceLevel }) {
  return (
    <span
      className={`inline-flex items-center border px-2 py-0.5 text-[11px] font-bold uppercase ${styles[level]}`}
    >
      {level}
    </span>
  );
}