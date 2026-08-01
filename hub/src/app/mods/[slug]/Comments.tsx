"use client";

import { useCallback, useEffect, useState } from "react";
import { MessageSquare, Reply, Trash2 } from "lucide-react";

interface Comment {
  id: string;
  parent_id: string | null;
  author: string | null;
  author_avatar: string | null;
  body_md: string | null;
  deleted: boolean;
  created_at: string;
}

interface Me {
  id: string;
  username: string;
  display_name: string | null;
  role: string;
}

export function Comments({ slug }: { slug: string }) {
  const [comments, setComments] = useState<Comment[]>([]);
  const [me, setMe] = useState<Me | null>(null);
  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    fetch(`/api/v1/mods/${slug}/comments`)
      .then((r) => (r.ok ? r.json() : { comments: [] }))
      .then((d) => setComments(d.comments))
      .catch(() => {});
  }, [slug]);

  useEffect(() => {
    load();
    fetch("/api/v1/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then(setMe)
      .catch(() => {});
  }, [load]);

  const post = async () => {
    if (!draft.trim() || busy) return;
    setBusy(true);
    await fetch(`/api/v1/mods/${slug}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body_md: draft.trim(), parent_id: replyTo ?? undefined }),
    });
    setDraft("");
    setReplyTo(null);
    setBusy(false);
    load();
  };

  const remove = async (id: string) => {
    await fetch(`/api/v1/comments/${id}`, { method: "DELETE" });
    load();
  };

  const roots = comments.filter((c) => !c.parent_id);
  const children = (id: string) => comments.filter((c) => c.parent_id === id);

  const Item = ({ c, depth }: { c: Comment; depth: number }) => (
    <div className={depth > 0 ? "ml-8 mt-3" : "mt-4"}>
      <div className="flex items-start gap-3">
        {c.author_avatar ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={c.author_avatar} alt="" className="w-7 h-7 rounded-full mt-0.5" />
        ) : (
          <div className="w-7 h-7 rounded-full bg-surface-card mt-0.5" />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs">
            <span className="font-semibold text-foreground">
              {c.deleted ? "[deleted]" : c.author}
            </span>
            <span className="text-text-dim">{c.created_at.slice(0, 10)}</span>
          </div>
          <p className="text-sm text-text-muted mt-1 whitespace-pre-wrap break-words">
            {c.deleted ? "This comment was deleted." : c.body_md}
          </p>
          {me && !c.deleted && (
            <div className="flex gap-3 mt-1">
              <button
                onClick={() => setReplyTo(replyTo === c.id ? null : c.id)}
                className="text-[11px] text-text-dim hover:text-foreground flex items-center gap-1"
              >
                <Reply className="w-3 h-3" />
                Reply
              </button>
              {(me.role !== "user" || (c.author ?? "") === (me.display_name ?? me.username)) && (
                <button
                  onClick={() => remove(c.id)}
                  className="text-[11px] text-text-dim hover:text-red-400 flex items-center gap-1"
                >
                  <Trash2 className="w-3 h-3" />
                  Delete
                </button>
              )}
            </div>
          )}
          {replyTo === c.id && me && (
            <div className="mt-2 flex gap-2">
              <input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && post()}
                placeholder={`Reply to ${c.author}…`}
                className="flex-1 px-3 py-1.5 text-sm rounded-lg bg-background border border-border text-foreground placeholder:text-text-dim focus:border-gold/60 focus:outline-none"
              />
              <button
                onClick={post}
                disabled={busy}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-gold text-background"
              >
                Post
              </button>
            </div>
          )}
        </div>
      </div>
      {children(c.id).map((child) => (
        <Item key={child.id} c={child} depth={depth + 1} />
      ))}
    </div>
  );

  return (
    <section>
      <h2 className="flex items-center gap-2 text-sm font-bold uppercase text-text-dim mb-3">
        <MessageSquare className="w-4 h-4" />
        Comments ({comments.filter((c) => !c.deleted).length})
      </h2>

      {me ? (
        replyTo === null && (
          <div className="flex gap-2">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && post()}
              placeholder="Add a comment…"
              className="flex-1 px-3 py-2 text-sm rounded-lg bg-background border border-border text-foreground placeholder:text-text-dim focus:border-gold/60 focus:outline-none"
            />
            <button
              onClick={post}
              disabled={busy || !draft.trim()}
              className="px-4 py-2 text-sm font-semibold rounded-lg bg-gold text-background disabled:opacity-40"
            >
              Post
            </button>
          </div>
        )
      ) : (
        <p className="text-sm text-text-dim">
          <a href={`/api/v1/auth/discord?next=/mods/${slug}`} className="text-gold hover:underline">
            Sign in
          </a>{" "}
          to join the discussion.
        </p>
      )}

      {roots.map((c) => (
        <Item key={c.id} c={c} depth={0} />
      ))}
    </section>
  );
}
