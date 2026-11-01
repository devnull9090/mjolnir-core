/**
 * A map's picture: its listing's first gallery image, or — for a map with
 * none — a tinted panel that still says which map it is. Fixed 16:9 so a
 * grid of them never shifts as images arrive.
 *
 * Decorative: every use sits beside the map's name, so no alt text.
 *
 * Plain `<img>`, as the map cards use: next/image needs an image loader the
 * Cloudflare build does not have, and gallery media is already sized.
 */
export function MapCover({
  src,
  code,
  priority = false,
  className = "",
}: {
  src: string | null;
  code: string;
  /** Above the fold: load now rather than lazily. */
  priority?: boolean;
  className?: string;
}) {
  return (
    <div className={`relative aspect-video overflow-hidden bg-surface-raised ${className}`}>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt=""
          width={640}
          height={360}
          loading={priority ? "eager" : "lazy"}
          fetchPriority={priority ? "high" : undefined}
          decoding="async"
          className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.04] motion-reduce:transition-none motion-reduce:group-hover:scale-100"
        />
      ) : (
        <div
          aria-hidden
          className="absolute inset-0 flex items-center justify-center bg-[radial-gradient(ellipse_at_30%_20%,#d4a84322,transparent_60%),linear-gradient(135deg,#1a2332,#0d1117)]"
        >
          <span className="font-mono text-4xl font-black tracking-[0.3em] text-white/10">{code}</span>
        </div>
      )}
    </div>
  );
}
