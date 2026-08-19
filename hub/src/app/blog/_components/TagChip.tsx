import Link from "next/link";

/**
 * A tag as a link to its filter page. `relative z-10` keeps the chip
 * clickable inside `PostCard`, whose title link is stretched over the whole
 * card.
 */
export function TagChip({ tag }: { tag: string }) {
  return (
    <Link
      href={`/blog/tag/${tag}`}
      className="relative z-10 rounded-md bg-gold/10 px-2 py-0.5 font-mono text-xs text-gold transition-colors hover:bg-gold/20"
    >
      {tag}
    </Link>
  );
}
