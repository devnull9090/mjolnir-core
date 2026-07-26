import type { CSSProperties, ReactNode } from "react";
import Link from "next/link";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";
import { slugify } from "@/lib/docs";

/**
 * Only the props that carry meaning are forwarded to the DOM. Spreading
 * react-markdown's props wholesale would leak its internal `node` object onto
 * the element and let a fenced block's `language-*` class replace the styling.
 */

type Kids = { children?: ReactNode };
type Anchored = Kids & { id?: string };
type Cell = Kids & { style?: CSSProperties };

const heading = "scroll-mt-28 font-bold text-foreground";
const linkStyle = "text-gold underline underline-offset-4 hover:text-foreground";

/** Rewrites relative `*.md` links onto their rendered hub route. */
function resolveHref(href: string): { href: string; external: boolean } {
  if (/^https?:\/\//i.test(href)) return { href, external: true };
  if (href.startsWith("#") || href.startsWith("/")) return { href, external: false };

  const [file, hash] = href.split("#");
  if (/\.md$/i.test(file)) {
    const target = `/docs/notes/${slugify(file.split("/").pop() ?? file)}`;
    return { href: hash ? `${target}#${hash}` : target, external: false };
  }
  return { href, external: false };
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
  p: ({ children }: Kids) => <p className="mt-4 text-sm leading-7 text-text-muted">{children}</p>,
  ul: ({ children }: Kids) => (
    <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-7 text-text-muted">{children}</ul>
  ),
  ol: ({ children }: Kids) => (
    <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm leading-7 text-text-muted">
      {children}
    </ol>
  ),
  li: ({ children }: Kids) => <li className="pl-1 marker:text-text-dim">{children}</li>,
  strong: ({ children }: Kids) => <strong className="font-bold text-foreground">{children}</strong>,
  em: ({ children }: Kids) => <em className="italic">{children}</em>,
  blockquote: ({ children }: Kids) => (
    <blockquote className="mt-5 border-l-2 border-gold/50 bg-gold/5 px-5 py-1">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="mt-10 border-border" />,
  a: ({ children, href }: Kids & { href?: string }) => {
    if (!href) return <>{children}</>;
    const resolved = resolveHref(href);
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
  },
  pre: ({ children }: Kids) => (
    <pre className="mt-5 overflow-x-auto border border-border bg-surface p-4 text-xs leading-6 text-text-muted">
      {children}
    </pre>
  ),
  // The pill styling is reset for `.markdown pre code` in globals.css, so fenced
  // blocks stay plain while inline code keeps the badge.
  code: ({ children }: Kids) => (
    <code className="border border-border bg-surface px-1.5 py-0.5 font-mono text-[0.85em] text-gold">
      {children}
    </code>
  ),
  table: ({ children }: Kids) => (
    <div className="mt-5 overflow-x-auto border border-border">
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

export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSlug]}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
