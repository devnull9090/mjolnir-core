import generated from "@/generated/blog.json";

/**
 * Posts are authored as Markdown in the repository `blog/` directory.
 * `scripts/sync-blog.mjs` snapshots them into `src/generated/blog.json` before
 * every build, so nothing here touches the filesystem — same reasoning as
 * `lib/changelog.ts`.
 */

export type BlogPost = {
  slug: string;
  /** ISO date, from the file name. */
  date: string;
  title: string;
  author: string;
  summary: string;
  tags: string[];
  body: string;
  sourceUrl: string;
};

const feed = generated as { posts: BlogPost[] };

/** Every post, newest first. */
export function getPosts(): BlogPost[] {
  return feed.posts;
}

export function getPost(slug: string): BlogPost | null {
  return feed.posts.find((p) => p.slug === slug) ?? null;
}

/** The posts either side of this one, for footer navigation. */
export function getAdjacentPosts(post: BlogPost): {
  newer: BlogPost | null;
  older: BlogPost | null;
} {
  const index = feed.posts.findIndex((p) => p.slug === post.slug);
  return {
    newer: index > 0 ? feed.posts[index - 1] : null,
    older: index >= 0 && index < feed.posts.length - 1 ? feed.posts[index + 1] : null,
  };
}

/** The most recent date any post carries, for sitemap and feed timestamps. */
export function getBlogLastModified(): Date {
  const newest = feed.posts[0];
  return newest ? new Date(`${newest.date}T00:00:00Z`) : new Date();
}
