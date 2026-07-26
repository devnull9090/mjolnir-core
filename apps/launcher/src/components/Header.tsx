export default function Header() {
  return (
    <header className="h-14 bg-surface-secondary/80 backdrop-blur-sm border-b border-border-subtle flex items-center justify-between px-6">
      <div className="flex items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-accent-green animate-pulse" />
        <span className="text-sm text-text-secondary">
          Halo Campaign Evolved
        </span>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-xs text-text-secondary px-3 py-1 rounded-full bg-surface-card border border-border-subtle">
          UE4SS v3.0.1
        </span>
        <span className="text-xs text-mjolnir-gold font-semibold">
          MJOLNIR v1.0
        </span>
      </div>
    </header>
  );
}
