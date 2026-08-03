/** Gold ring spinner, matching the launcher's. */
export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`inline-block shrink-0 animate-spin rounded-full border-2 border-mjolnir-gold border-t-transparent ${className}`}
    />
  );
}

/**
 * Shown while the app looks for an installation and reads its catalogue.
 *
 * Without this the setup form appears for the fraction of a second before
 * detection answers, which reads as "no installation found" when there is one.
 */
export function LoadingPanel({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="flex w-full max-w-xl flex-col items-center">
        <h1 className="text-xl font-bold text-mjolnir-gold">MJOLNIR Tag Editor</h1>
        <div className="mt-6 flex items-center gap-3">
          <Spinner className="h-5 w-5" />
          <span className="text-sm text-text-secondary">{label}</span>
        </div>
      </div>
    </div>
  );
}
