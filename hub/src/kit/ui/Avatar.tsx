/**
 * A Discord avatar, or the placeholder disc that stands in without one.
 *
 * Its own module rather than a piece of primitives.tsx because the profile
 * view renders on the website's server, and anything reachable from a Server
 * Component must not drag in the kit's React context. This file imports
 * nothing but its own styles.
 *
 * Plain `<img>`, not next/image: these components also render inside the
 * launcher's Vite build, where next/image does not exist. The image is
 * decorative — every use sits beside the name it belongs to — so the alt
 * text is empty rather than a redundant repeat of that name.
 */

const SIZES = { xs: "w-5 h-5", sm: "w-7 h-7", lg: "w-20 h-20" } as const;

export function Avatar({
  url,
  size = "sm",
  className = "",
}: {
  url: string | null | undefined;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  const px = SIZES[size];
  if (!url) {
    return (
      <div
        aria-hidden
        className={`${px} shrink-0 rounded-full bg-[var(--mj-surface-hover)] ${className}`}
      />
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={url} alt="" className={`${px} shrink-0 rounded-full object-cover ${className}`} />
  );
}
