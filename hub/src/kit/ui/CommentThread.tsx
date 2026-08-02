/**
 * A mod's comment thread. The API returns a flat list with `parent_id`
 * links; assembling the tree is the client's job, so it happens once here
 * for both the website and the launcher.
 *
 * Delete is offered on the author's own comments and on everything to a
 * moderator — the same rule the API enforces, mirrored in the UI only so the
 * button does not appear where it would fail.
 *
 * `CommentItem` and the composer are declared at module level rather than
 * inside the component: a component defined during render is a new type on
 * every render, so React would remount the composer's input and drop focus
 * after each keystroke.
 */
import { useCallback, useEffect, useState } from "react";

import { HubError } from "../client";
import type { Comment, User } from "../types";
import { useHub } from "./context";
import { timeAgo } from "./format";
import { MessageIcon, ReplyIcon, TrashIcon } from "./icons";
import { ActionButton, ErrorNote } from "./primitives";

function Composer({
  value,
  onChange,
  onPost,
  busy,
  placeholder,
  autoFocus = false,
}: {
  value: string;
  onChange: (v: string) => void;
  onPost: () => void;
  busy: boolean;
  placeholder: string;
  autoFocus?: boolean;
}) {
  return (
    <div className="flex gap-2">
      <input
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onPost();
        }}
        placeholder={placeholder}
        maxLength={8192}
        className="flex-1 min-w-0 px-3 py-2 text-sm rounded-lg bg-[var(--mj-bg)] border border-[var(--mj-border)] text-[var(--mj-text)] placeholder:text-[var(--mj-text-dim)] focus:border-[var(--mj-gold)]/60 focus:outline-none"
      />
      <ActionButton onClick={onPost} disabled={busy || !value.trim()}>
        Post
      </ActionButton>
    </div>
  );
}

function CommentItem({
  comment,
  depth,
  comments,
  user,
  replyTo,
  setReplyTo,
  onDelete,
  composer,
}: {
  comment: Comment;
  depth: number;
  comments: Comment[];
  user: User | null;
  replyTo: string | null;
  setReplyTo: (id: string | null) => void;
  onDelete: (id: string) => void;
  composer: (placeholder: string) => React.ReactNode;
}) {
  const mayDelete =
    !!user && !comment.deleted && (user.role !== "user" || comment.author_id === user.id);
  const replies = comments.filter((c) => c.parent_id === comment.id);

  return (
    <div className={depth > 0 ? "ml-8 mt-3" : "mt-4"}>
      <div className="flex items-start gap-3">
        {comment.author_avatar ? (
          // Plain <img>, not next/image: these components also render inside
          // the launcher's Vite build, where next/image does not exist.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={comment.author_avatar} alt="" className="w-7 h-7 rounded-full mt-0.5" />
        ) : (
          <div className="w-7 h-7 rounded-full bg-[var(--mj-surface-raised)] mt-0.5" />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs">
            <span className="font-semibold text-[var(--mj-text)]">
              {comment.deleted ? "[deleted]" : comment.author}
            </span>
            <span className="text-[var(--mj-text-dim)]">{timeAgo(comment.created_at)}</span>
          </div>
          <p className="text-sm text-[var(--mj-text-muted)] mt-1 whitespace-pre-wrap break-words">
            {comment.deleted ? "This comment was deleted." : comment.body_md}
          </p>
          {user && !comment.deleted && (
            <div className="flex gap-3 mt-1">
              <button
                type="button"
                onClick={() => setReplyTo(replyTo === comment.id ? null : comment.id)}
                className="text-[11px] text-[var(--mj-text-dim)] hover:text-[var(--mj-text)] flex items-center gap-1 cursor-pointer"
              >
                <ReplyIcon className="w-3 h-3" />
                Reply
              </button>
              {mayDelete && (
                <button
                  type="button"
                  onClick={() => onDelete(comment.id)}
                  className="text-[11px] text-[var(--mj-text-dim)] hover:text-[var(--mj-red)] flex items-center gap-1 cursor-pointer"
                >
                  <TrashIcon className="w-3 h-3" />
                  Delete
                </button>
              )}
            </div>
          )}
          {replyTo === comment.id && user && (
            <div className="mt-2">{composer(`Reply to ${comment.author}…`)}</div>
          )}
        </div>
      </div>
      {replies.map((child) => (
        <CommentItem
          key={child.id}
          comment={child}
          depth={depth + 1}
          comments={comments}
          user={user}
          replyTo={replyTo}
          setReplyTo={setReplyTo}
          onDelete={onDelete}
          composer={composer}
        />
      ))}
    </div>
  );
}

export function CommentThread({ slug }: { slug: string }) {
  const { client, user, signIn } = useHub();
  const [comments, setComments] = useState<Comment[]>([]);
  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    client
      .listComments(slug)
      .then(setComments)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [client, slug]);

  useEffect(load, [load]);

  const post = useCallback(async () => {
    const body = draft.trim();
    if (!body || busy) return;
    setBusy(true);
    setError(null);
    try {
      await client.postComment(slug, body, replyTo ?? undefined);
      setDraft("");
      setReplyTo(null);
      load();
    } catch (e) {
      setError(
        e instanceof HubError && e.status === 429
          ? "You are posting faster than the hub accepts. Try again shortly."
          : e instanceof Error
            ? e.message
            : String(e),
      );
    } finally {
      setBusy(false);
    }
  }, [busy, client, draft, load, replyTo, slug]);

  const remove = useCallback(
    async (id: string) => {
      setError(null);
      try {
        await client.deleteComment(id);
        load();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [client, load],
  );

  const composer = useCallback(
    (placeholder: string) => (
      <Composer
        value={draft}
        onChange={setDraft}
        onPost={() => void post()}
        busy={busy}
        placeholder={placeholder}
        autoFocus={replyTo !== null}
      />
    ),
    [busy, draft, post, replyTo],
  );

  const roots = comments.filter((c) => !c.parent_id);

  return (
    <section>
      <h2 className="flex items-center gap-2 text-sm font-bold uppercase text-[var(--mj-text-dim)] mb-3">
        <MessageIcon className="w-4 h-4" />
        Comments ({comments.filter((c) => !c.deleted).length})
      </h2>

      {error && (
        <div className="mb-3">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}

      {user ? (
        replyTo === null && composer("Add a comment…")
      ) : (
        <p className="text-sm text-[var(--mj-text-dim)]">
          <button
            type="button"
            onClick={signIn}
            className="text-[var(--mj-gold)] hover:underline cursor-pointer"
          >
            Sign in
          </button>{" "}
          to join the discussion.
        </p>
      )}

      {roots.map((c) => (
        <CommentItem
          key={c.id}
          comment={c}
          depth={0}
          comments={comments}
          user={user}
          replyTo={replyTo}
          setReplyTo={setReplyTo}
          onDelete={(id) => void remove(id)}
          composer={composer}
        />
      ))}
    </section>
  );
}
