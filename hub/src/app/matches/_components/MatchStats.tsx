/** A compact row of figures, centred, for a podium step or a hero. */
export function MatchStats({ items, className = "" }: { items: [string, string | number][]; className?: string }) {
  return (
    <dl className={`grid grid-cols-3 divide-x divide-border rounded-xl border border-border bg-background/40 ${className}`}>
      {items.map(([label, value]) => (
        <div key={label} className="px-2 py-2">
          <dt className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">{label}</dt>
          <dd className="text-lg font-black tabular-nums text-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
