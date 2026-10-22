import type { CSSProperties, ReactNode } from "react";
import Link from "next/link";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";
import { getDocNotes, getGuides, slugify } from "@/lib/docs";
import { CompareImage } from "./CompareImage";
import { ZoomableImages } from "./ZoomableImages";

/**
 * Only the props that carry meaning are forwarded to the DOM. Spreading
 * react-markdown's props wholesale would leak its internal `node` object onto
 * the element and let a fenced block's `language-*` class replace the styling.
 */

type Kids = { children?: ReactNode };
type Anchored = Kids & { id?: string };
type Cell = Kids & { style?: CSSProperties };

const heading = "scroll-mt-28 break-words font-bold text-foreground";
const linkStyle = "text-gold underline underline-offset-4 hover:text-foreground";

const REPO_BLOB = "https://github.com/devnull9090/mjolnir-core/blob/main";
const noteSlugs = new Set(getDocNotes().map((note) => note.slug));
const guideSlugs = new Set(getGuides().map((guide) => guide.slug));

/** Resolves `.` and `..` segments; null when the path climbs out of the repository. */
function normalizePath(path: string): string | null {
  const parts: string[] = [];
  for (const part of path.split("/")) {
    if (part === "" || part === ".") continue;
    if (part !== "..") parts.push(part);
    else if (parts.pop() === undefined) return null;
  }
  return parts.join("/");
}

/**
 * Rewrites a relative link onto where it is actually served.
 *
 * With `source` (the repository directory the Markdown was authored in), a
 * link is resolved the way GitHub resolves it: a published note or guide goes
 * to its hub route, and anything else (source files, `docs/re/`, a doc in
 * neither list) goes to the file on GitHub, which a relative link here would
 * miss with a 404. Notes and guides link to each other by file name, so the
 * two routes have to be told apart.
 *
 * Without `source` only `*.md` links are rewritten, onto the notes route.
 */
function resolveHref(href: string, source?: string): { href: string; external: boolean } {
  if (/^https?:\/\//i.test(href)) return { href, external: true };
  if (href.startsWith("#") || href.startsWith("/") || /^[a-z][a-z\d+.-]*:/i.test(href)) {
    return { href, external: false };
  }

  const [file, hash] = href.split("#");
  const suffix = hash ? `#${hash}` : "";
  if (source) {
    const path = normalizePath(`${source}/${file}`);
    if (path === null) return { href, external: false };
    if (/^docs\/[^/]+\.md$/i.test(path)) {
      const slug = slugify(path.slice("docs/".length));
      if (noteSlugs.has(slug)) return { href: `/docs/notes/${slug}${suffix}`, external: false };
      if (guideSlugs.has(slug)) return { href: `/docs/guides/${slug}${suffix}`, external: false };
    }
    return { href: `${REPO_BLOB}/${path}${suffix}`, external: true };
  }
  if (/\.md$/i.test(file)) {
    const target = `/docs/notes/${slugify(file.split("/").pop() ?? file)}`;
    return { href: `${target}${suffix}`, external: false };
  }
  return { href, external: false };
}

/** Links resolve against the Markdown's source directory, so one renderer per source. */
function makeLink(source?: string): Components["a"] {
  return function MarkdownLink({ children, href }: Kids & { href?: string }) {
    if (!href) return <>{children}</>;
    const resolved = resolveHref(href, source);
    if (resolved.external) {
      return (
        <a href={resolved.href} target="_blank" rel="noreferrer" className={linkStyle}>
          {children}
        </a>
      );
    }
    return (
      <Link href={resolved.href} className={linkStyle}>
        {children}
      </Link>
    );
  };
}

const components: Components = {
  // Notes render their own page H1, so a stray H1 in the body becomes an H2.
  h1: ({ children, id }: Anchored) => (
    <h2 id={id} className={`${heading} mt-12 border-b border-border pb-3 text-2xl`}>
      {children}
    </h2>
  ),
  h2: ({ children, id }: Anchored) => (
    <h2 id={id} className={`${heading} mt-12 border-b border-border pb-3 text-2xl`}>
      {children}
    </h2>
  ),
  h3: ({ children, id }: Anchored) => (
    <h3 id={id} className={`${heading} mt-9 text-lg`}>
      {children}
    </h3>
  ),
  h4: ({ children, id }: Anchored) => (
    <h4 id={id} className={`${heading} mt-7 text-base`}>
      {children}
    </h4>
  ),
  p: ({ children }: Kids) => (
    <p className="mt-4 break-words text-sm leading-7 text-text-muted">{children}</p>
  ),
  ul: ({ children }: Kids) => (
    <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-7 text-text-muted">{children}</ul>
  ),
  ol: ({ children }: Kids) => (
    <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm leading-7 text-text-muted">
      {children}
    </ol>
  ),
  li: ({ children }: Kids) => <li className="break-words pl-1 marker:text-text-dim">{children}</li>,
  strong: ({ children }: Kids) => <strong className="font-bold text-foreground">{children}</strong>,
  em: ({ children }: Kids) => <em className="italic">{children}</em>,
  blockquote: ({ children }: Kids) => (
    <blockquote className="mt-5 border-l-2 border-gold/50 bg-gold/5 px-5 py-1">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="mt-10 border-border" />,
  /**
   * A plain `img`, not `next/image`. Markdown carries no intrinsic dimensions,
   * and the optimizer is not wired up on Cloudflare, so the component would
   * need `fill` plus a sized wrapper to render a screenshot whose size is only
   * known at author time. These are pre-sized and small; the alt text becomes
   * the caption, since a guide's screenshots are worth labelling.
   *
   * The button is the lightbox's trigger: <ZoomableImages> below catches its
   * click, so this stays server-rendered.
   */
  img: ({ src, alt }: { src?: string | Blob; alt?: string }) => {
    if (typeof src !== "string") return null;
    // `after.jpg?before=before.jpg`: a before-and-after pair (CompareImage).
    const pair = src.match(/^([^?]+)\?before=([^&]+)$/);
    if (pair) {
      return <CompareImage after={pair[1]} before={decodeURIComponent(pair[2])} alt={alt ?? ""} />;
    }
    // Spans, not figure/figcaption: Markdown wraps a standalone image in a
    // paragraph, and flow content inside a `p` is invalid HTML that React
    // reports as a hydration error.
    return (
      <span className="mt-6 block">
        <button
          type="button"
          data-zoom
          aria-label={alt ? `Enlarge: ${alt}` : "Enlarge image"}
          className="block w-full cursor-zoom-in"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={alt ?? ""}
            loading="lazy"
            className="block w-full border border-border bg-surface transition-colors hover:border-gold/50"
          />
        </button>
        {alt && <span className="mt-2 block text-xs leading-6 text-text-dim">{alt}</span>}
      </span>
    );
  },
  a: makeLink(),
  pre: ({ children }: Kids) => (
    <pre className="mt-5 overflow-x-auto border border-border bg-surface p-4 text-xs leading-6 text-text-muted">
      {children}
    </pre>
  ),
  // The pill styling and the `break-all` are reset for `.markdown pre code` in
  // globals.css, so fenced blocks stay plain and scroll horizontally while
  // inline code keeps the badge and breaks long paths instead of overflowing.
  code: ({ children }: Kids) => (
    <code className="border border-border bg-surface px-1.5 py-0.5 font-mono text-[0.85em] break-all text-gold">
      {children}
    </code>
  ),
  table: ({ children }: Kids) => (
    <div className="scroll-hint mt-5 overflow-x-auto border border-border">
      <table className="w-full min-w-[420px] text-left text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }: Kids) => (
    <thead className="bg-surface text-xs uppercase text-text-dim">{children}</thead>
  ),
  tbody: ({ children }: Kids) => <tbody className="divide-y divide-border">{children}</tbody>,
  th: ({ children, style }: Cell) => (
    <th style={style} className="px-4 py-3 font-bold">
      {children}
    </th>
  ),
  td: ({ children, style }: Cell) => (
    <td style={style} className="px-4 py-3 align-top leading-6 text-text-muted">
      {children}
    </td>
  ),
};

/**
 * `source` is the repository directory the Markdown was authored in (`docs`
 * for notes and guides). Pass it when the text is a repository file, so its
 * relative links resolve; leave it out for anything else.
 */
export function Markdown({ children, source }: { children: string; source?: string }) {
  return (
    <div className="markdown">
      <ZoomableImages>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeSlug]}
          components={source ? { ...components, a: makeLink(source) } : components}
        >
          {children}
        </ReactMarkdown>
      </ZoomableImages>
    </div>
  );
}
