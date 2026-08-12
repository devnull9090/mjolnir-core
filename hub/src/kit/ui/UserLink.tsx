/**
 * Someone's name, pointing at their profile — however this app reaches one.
 *
 * The two hosts navigate in ways that have nothing in common, so both are
 * offered through the context and this picks whichever is there:
 *
 *   website   `profileHref` → a real <a href="/users/{id}">, so middle-click,
 *             open-in-new-tab and crawlers all behave.
 *   launcher  `openProfile` → a <button>, because the launcher's views are
 *             component state, not URLs; an anchor would navigate the whole
 *             webview off the app.
 *   neither   plain text. A host that cannot show a profile should not be
 *             made to render something that looks clickable.
 *
 * Kept out of primitives.tsx deliberately: it reads the React context, and
 * anything the website's Server Components can reach must not.
 */
import { useHub } from "./context";

const LINK_CLASS = "hover:text-[var(--mj-gold)] transition-colors";

export function UserLink({
  userId,
  name,
  className = "",
}: {
  userId: string | null | undefined;
  name: string;
  className?: string;
}) {
  const { profileHref, openProfile } = useHub();
  if (!userId) return <span className={className}>{name}</span>;

  if (openProfile) {
    return (
      <button
        type="button"
        onClick={() => openProfile(userId)}
        className={`${LINK_CLASS} cursor-pointer ${className}`}
      >
        {name}
      </button>
    );
  }

  const href = profileHref?.(userId);
  if (!href) return <span className={className}>{name}</span>;
  return (
    <a href={href} className={`${LINK_CLASS} ${className}`}>
      {name}
    </a>
  );
}
