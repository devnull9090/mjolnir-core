import Link from "next/link";

import type { BlogPost } from "@/lib/blog";
import { formatPostDate } from "@/lib/blog";
import { TagChip } from "./TagChip";

/**
 * One post on a listing page (the index and the tag pages). The title link is
 * stretched over the card via its `after` pseudo-element, so the whole card
 * stays clickable without wrapping the tag links in a second anchor.
 */
export function PostCard({ post }: { post: BlogPost }) {
  return (
    <article className="relative rounded-xl border border-border bg-surface-raised p-5 transition-colors hover:border-gold/40">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <Link
          href={`/blog/${post.slug}`}
          className="text-lg font-bold text-foreground after:absolute after:inset-0"
        >
          {post.title}
        </Link>
        <time dateTime={post.date} className="font-mono text-xs text-text-dim">
          {formatPostDate(post.date)}
        </time>
      </div>
      <p className="mt-2 text-sm leading-6 text-text-muted">{post.summary}</p>
      {post.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {post.tags.map((tag) => (
            <TagChip key={tag} tag={tag} />
          ))}
        </div>
      )}
    </article>
  );
}
