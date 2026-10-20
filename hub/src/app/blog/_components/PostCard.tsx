import Link from "next/link";

import type { BlogPost } from "@/lib/blog";
import { formatPostDate } from "@/lib/blog";
import { TagChip } from "./TagChip";

/**
 * One post on a listing page (the index and the tag pages). The title link is
 * stretched over the card via its `after` pseudo-element, so the whole card
 * stays clickable without wrapping the tag links in a second anchor.
 *
 * A post with a featured image (`**Image:**`) shows it beside the text, or
 * above it on a phone. A plain `img` for the reason in Markdown.tsx; empty alt
 * because the title link beside it already names the post.
 */
export function PostCard({ post }: { post: BlogPost }) {
  return (
    <article className="relative flex flex-col gap-4 rounded-xl border border-border bg-surface-raised p-5 transition-colors hover:border-gold/40 sm:flex-row sm:items-start sm:gap-5">
      {post.image && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={post.image}
          alt=""
          loading="lazy"
          width={1200}
          height={630}
          className="block aspect-[1200/630] w-full shrink-0 rounded-lg border border-border bg-surface object-cover sm:w-60"
        />
      )}
      <div className="min-w-0 flex-1">
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
      </div>
    </article>
  );
}
