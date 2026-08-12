/**
 * A profile's head and figures: who someone is, and what they have done.
 *
 * Rendered identically by the website and the launcher, which is the whole
 * point — the two disagreeing about what an account's numbers are would be
 * worse than either of them being slightly wrong.
 *
 * Deliberately hook-free, like ChangeList: the website renders it in a
 * Server Component straight from D1, while the launcher hands it the payload
 * of one API call. The mods themselves are not here, because the two hosts
 * do genuinely different things with a card — the website links it, the
 * launcher opens a detail pane with an Install button beside it.
 */
import type { UserProfile } from "../types";
import { Avatar } from "./Avatar";
import { formatCount } from "./format";

/** SQLite writes "YYYY-MM-DD HH:MM:SS" and means UTC; `new Date` does not. */
function joinedOn(sqlite: string): string {
  const parsed = new Date(sqlite.includes("T") ? sqlite : `${sqlite.replace(" ", "T")}Z`);
  if (Number.isNaN(parsed.getTime())) return sqlite.slice(0, 10);
  return parsed.toLocaleDateString("en-GB", { year: "numeric", month: "long", timeZone: "UTC" });
}

/** One figure and what it counts. */
function Stat({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div
      title={title}
      className="rounded-xl border border-[var(--mj-border)] bg-[var(--mj-surface)] px-4 py-3 min-w-0"
    >
      <div className="text-2xl font-black text-[var(--mj-text)] tabular-nums">{value}</div>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--mj-text-dim)] mt-0.5">
        {label}
      </div>
    </div>
  );
}

function Band({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-sm font-bold uppercase text-[var(--mj-text-dim)] mb-3">{title}</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{children}</div>
    </section>
  );
}

/**
 * The two bands read in opposite directions on purpose: the first is what
 * this account's work drew from everyone else, the second is what it did.
 * Collapsing them into one grid of eight numbers loses that distinction, and
 * the distinction is most of the meaning.
 */
export function ProfileSummary({ profile }: { profile: UserProfile }) {
  const { user, stats } = profile;
  const name = user.display_name ?? user.username;
  const role = user.role === "user" ? null : user.role;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center gap-5">
        <Avatar url={user.avatar_url} size="lg" className="border border-[var(--mj-border)]" />
        <div className="min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-3xl md:text-4xl font-black text-[var(--mj-text)] break-words">
              {name}
            </h1>
            {role && (
              <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-[var(--mj-gold)]/15 text-[var(--mj-gold)]">
                {role}
              </span>
            )}
          </div>
          <p className="text-[var(--mj-text-muted)] mt-1">
            {user.display_name && user.display_name !== user.username ? (
              <span className="text-[var(--mj-text-dim)]">{user.username} · </span>
            ) : null}
            Member since {joinedOn(user.created_at)}
          </p>
        </div>
      </header>

      <Band title="Published work">
        <Stat label="Mods published" value={String(stats.mods_published)} />
        <Stat
          label="Downloads"
          value={formatCount(stats.downloads_received)}
          title={`${stats.downloads_received} downloads across their published mods`}
        />
        <Stat
          label="Page views"
          value={formatCount(stats.views_received)}
          title={`${stats.views_received} views across their published mods`}
        />
        <Stat
          label="Rating"
          value={stats.rating_mean === null ? "—" : `${stats.rating_mean.toFixed(1)}★`}
          title={
            stats.ratings_received > 0
              ? `Weighted across ${stats.ratings_received} rating${stats.ratings_received === 1 ? "" : "s"}`
              : "No ratings yet"
          }
        />
      </Band>

      <Band title="Activity">
        <Stat
          label="Mods downloaded"
          value={formatCount(stats.mods_downloaded)}
          title="Distinct mods downloaded while signed in. Anonymous downloads are never attributed, and none before August 2026 were recorded."
        />
        <Stat label="Ratings given" value={formatCount(stats.ratings_given)} />
        <Stat label="Comments" value={formatCount(stats.comments_posted)} />
        <Stat
          label="Screenshots"
          value={formatCount(stats.media_contributed)}
          title="Gallery items they submitted that a moderator approved"
        />
      </Band>
    </div>
  );
}
