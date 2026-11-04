/**
 * The hammer mark, at the size the navbar and footer draw it. Served as a
 * 64 px WebP (3 KB, sharp on a 2x screen) rather than the 1024 px source
 * PNG (1.2 MB) that every page used to download for a 32 px icon.
 * Decorative: it always sits beside the "MJOLNIR" wordmark.
 */
export function Logo({ className = "w-8 h-8" }: { className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- static asset, already sized; no loader on Cloudflare
    <img src="/logo-64.webp" alt="" width={32} height={32} className={`${className} object-contain`} />
  );
}
