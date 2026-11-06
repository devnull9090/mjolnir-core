import Link from "next/link";
import type { ReactNode } from "react";

import { PlayerAvatar } from "../../components/ui";
import type { MatchSummary, PlayerTotals } from "@/lib/api/matches";
import type { PlayerRecord, RecordMark, RecordRival } from "@/lib/api/player-record";
import { MatchGrid } from "../../matches/_components/MatchCard";
import { MatchMap } from "../../matches/_components/MatchMap";
import { PositionMap } from "../../matches/_components/PositionMap";
import previews from "../../matches/_components/map-previews.json";
import type { DeathMark, KillMark } from "../../matches/_components/positions";
import { kd, playerHref, weaponName } from "../../matches/_components/format";
import { LocalTime } from "../../matches/_components/LocalTime";
import { CareerRing } from "./CareerRing";
import { FormLine } from "./FormLine";
import { recordDisplay } from "./font";
import {
  MEDALS,
  WEAPON_CLASSES,
  medalTotal,
  personalBests,
  playedTime,
  runningRatio,
  styleShares,
  styleTitle,
  winRate,
  type MedalInfo,
} from "./record";

/** How many maps the map list offers before the rest fold away. */
const MAPS_LISTED = 8;

/** Names run from three letters to a clan tag: the longer, the smaller, so none breaks mid-word. */
function nameSize(name: string): string {
  if (name.length <= 10) return "text-[clamp(3.25rem,9vw,7rem)]";
  if (name.length <= 16) return "text-[clamp(2.75rem,6.5vw,5.25rem)]";
  return "text-[clamp(2.25rem,5vw,4rem)]";
}

/**
 * A player's whole record. `standalone` is the name page's full-width hero;
 * a profile page already has its own header, so there the hero sits in the
 * page's column without the name.
 */
export function PlayerRecordView({
  name,
  avatar,
  totals,
  record,
  marks,
  mapCode,
  mapHref,
  matches,
  matchesFooter,
  reports,
  standalone,
  aside,
  note,
}: {
  name: string;
  avatar: { avatar_url: string | null } | null;
  totals: PlayerTotals;
  record: PlayerRecord;
  marks: RecordMark[];
  mapCode: string | null;
  /** The link that shows another map on this page. */
  mapHref: (code: string) => string;
  matches: MatchSummary[];
  matchesFooter?: ReactNode;
  reports?: number;
  standalone: boolean;
  aside?: ReactNode;
  /** What this record covers, under the hero's figures. */
  note?: ReactNode;
}) {
  const shares = styleShares(record.weapons);
  const title = styleTitle(shares);
  const topMap = record.maps[0];
  const topWeapon = record.weapons[0];
  const bests = personalBests(record.matches);
  const ratios = runningRatio(record.matches);
  const fought = record.matches.length > 0;

  const hero = (
    <div className={`relative grid items-center gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,520px)] ${standalone ? "mx-auto max-w-6xl px-4 sm:px-6" : ""}`}>
      <div className="min-w-0">
        {aside}
        <p className="flex flex-wrap items-center gap-3 text-xs font-semibold uppercase tracking-[0.22em] text-text-muted">
          Combat record
          {title && <span className="rounded-sm bg-gold px-2 py-0.5 tracking-[0.14em] text-background">{title}</span>}
        </p>
        {standalone && (
          <h1 className={`record-display mt-3 break-words leading-[0.92] text-foreground ${nameSize(name)}`}>{name}</h1>
        )}
        <p className="mt-4 max-w-md text-base leading-relaxed text-text-muted">
          {topMap && topWeapon ? (
            <>
              Most at home on <span className="text-foreground">{topMap.title ?? topMap.code}</span> with the{" "}
              <span className="text-foreground">{weaponName(topWeapon.weapon)}</span>.{" "}
            </>
          ) : null}
          {totals.last_played && (
            <>
              Last played <LocalTime sql={totals.last_played} showAgo={false} />.
            </>
          )}
        </p>

        <div className="mt-8 flex flex-col gap-6 sm:flex-row sm:items-end sm:gap-8">
          <div>
            <p className="record-display text-[clamp(5rem,12vw,8.5rem)] leading-[0.82] text-gold tabular-nums">{kd(totals.kills, totals.deaths)}</p>
            <p className="mt-2 text-xs font-semibold uppercase tracking-[0.18em] text-text-muted">Kills per death</p>
          </div>
          <dl className="grid flex-1 grid-cols-2 gap-x-6 gap-y-3 sm:border-l sm:border-border sm:pl-6">
            <Figure
              label="Win rate"
              value={winRate(totals.wins, totals.losses, totals.draws)}
              hint={`${totals.wins} of ${totals.wins + totals.losses + totals.draws} finished`}
            />
            <Figure label="In matches" value={playedTime(record.time_played_ms)} />
            <Figure label="Kills" value={totals.kills.toLocaleString("en-US")} />
            <Figure label="Deaths" value={totals.deaths.toLocaleString("en-US")} />
          </dl>
        </div>

        <dl className="mt-8 grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-5 [&>*:last-child]:col-span-2 sm:[&>*:last-child]:col-span-1">
          <Ledger label="Matches" value={totals.matches} />
          <Ledger label="Wins" value={totals.wins} />
          <Ledger label="Assists" value={record.assists} />
          <Ledger label="Medals" value={medalTotal(record)} />
          {reports !== undefined ? <Ledger label="Reports" value={reports} /> : <Ledger label="Captures" value={totals.captures} />}
        </dl>
        {note && <p className="mt-4 max-w-lg text-xs leading-relaxed text-text-dim">{note}</p>}
      </div>

      {fought && (
        <CareerRing
          matches={record.matches}
          summary={`${name}'s career signature: ${record.matches.length} matches, each drawn as a spoke of kills and deaths.`}
          center={
            <>
              <PlayerAvatar name={name} user={avatar} size="xl" />
              <span className="mt-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-text-muted">Signature</span>
            </>
          }
        />
      )}
    </div>
  );

  return (
    <div className={recordDisplay.variable}>
      {standalone ? (
        <header className="record-hero relative overflow-hidden pb-14 pt-44 sm:pt-32">{hero}</header>
      ) : (
        <div className="record-hero relative overflow-hidden rounded-2xl border border-border p-6 sm:p-8">{hero}</div>
      )}

      <div className={standalone ? "mx-auto max-w-6xl px-4 pb-20 sm:px-6" : ""}>
        {fought && (
          <Chapter id="form" title="Form">
            <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_260px]">
              <div>
                <p className="mb-3 text-sm text-text-muted">Career kills per death, match by match. Above the dashed line, more kills than deaths.</p>
                <FormLine matches={record.matches} ratios={ratios} />
              </div>
              <dl className="flex flex-col divide-y divide-border border-y border-border">
                <Best label="Most kills in a match" value={bests.mostKills?.kills} href={bests.mostKills && `/matches/${bests.mostKills.id}`} sub={bests.mostKills?.map_title} />
                <Best
                  label="Best match K/D"
                  value={bests.bestRatio ? kd(bests.bestRatio.kills, bests.bestRatio.deaths) : undefined}
                  href={bests.bestRatio && `/matches/${bests.bestRatio.id}`}
                  sub={bests.bestRatio ? `${bests.bestRatio.kills}–${bests.bestRatio.deaths}` : null}
                />
                <Best label="Wins in a row" value={bests.winStreak || undefined} />
              </dl>
            </div>
          </Chapter>
        )}

        {record.maps.length > 0 && (
          <Chapter id="battlegrounds" title="Battlegrounds">
            <Battlegrounds record={record} marks={marks} mapCode={mapCode} mapHref={mapHref} />
          </Chapter>
        )}

        {(record.weapons.length > 0 || record.rivals.length > 0) && (
          <div className="grid gap-x-12 lg:grid-cols-2">
            {record.weapons.length > 0 && (
              <Chapter id="arsenal" title="Arsenal">
                <Arsenal record={record} shares={shares} />
              </Chapter>
            )}
            {record.rivals.length > 0 && (
              <Chapter id="rivals" title="Rivals">
                <Rivals rivals={record.rivals} />
              </Chapter>
            )}
          </div>
        )}

        {fought && (
          <Chapter id="medals" title="Medal case">
            <MedalCase medals={record.medals} />
          </Chapter>
        )}

        <Chapter id="matches" title="Matches">
          <MatchGrid matches={matches} />
          {matchesFooter}
        </Chapter>
      </div>
    </div>
  );
}

function Figure({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">{label}</dt>
      <dd className="record-display whitespace-nowrap text-3xl leading-tight text-foreground tabular-nums">{value}</dd>
      {hint && <dd className="text-[11px] tabular-nums text-text-dim">{hint}</dd>}
    </div>
  );
}

function Ledger({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-surface/80 px-3 py-2.5">
      <dt className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">{label}</dt>
      <dd className="text-lg font-bold text-foreground tabular-nums">{value.toLocaleString("en-US")}</dd>
    </div>
  );
}

function Best({ label, value, sub, href }: { label: string; value: ReactNode; sub?: string | null; href?: string | null }) {
  const body = (
    <>
      <dt className="text-xs text-text-muted">{label}</dt>
      <dd className="flex items-baseline justify-between gap-3">
        <span className="record-display text-4xl text-foreground tabular-nums">{value ?? "–"}</span>
        {sub && <span className="truncate text-xs text-text-dim">{sub}</span>}
      </dd>
    </>
  );
  return href ? (
    <Link href={href} className="block flex-1 py-3 hover:bg-surface-hover/40">{body}</Link>
  ) : (
    <div className="flex-1 py-3">{body}</div>
  );
}

function Chapter({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="mt-16 min-w-0 scroll-mt-28">
      <div className="mb-6 flex items-center gap-4">
        <h2 id={id} className="record-display text-4xl text-foreground">{title}</h2>
        <span aria-hidden className="h-px flex-1 bg-gradient-to-r from-gold/50 to-transparent" />
      </div>
      {children}
    </section>
  );
}

function Battlegrounds({
  record,
  marks,
  mapCode,
  mapHref,
}: {
  record: PlayerRecord;
  marks: RecordMark[];
  mapCode: string | null;
  mapHref: (code: string) => string;
}) {
  const current = record.maps.find((m) => m.code === mapCode) ?? record.maps[0];
  const { kills, deaths } = plotted(marks);
  const legend: [string, string] = ["where they killed", "where they died"];
  const plain = <PositionMap kills={kills} deaths={deaths} legend={legend} />;
  // A selected map past the fold still gets its row.
  const listed = record.maps.slice(0, MAPS_LISTED);
  if (!listed.includes(current)) listed[listed.length - 1] = current;
  const busiest = Math.max(...listed.map((m) => m.kills + m.deaths), 1);

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0">
        {marks.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border-bright p-10 text-center text-sm text-text-muted">
            No positions were reported on this map.
          </p>
        ) : current.code in previews ? (
          <MatchMap key={current.code} code={current.code} kills={kills} deaths={deaths} time={null} fresh={10000} fallback={plain} legend={legend} wide />
        ) : (
          plain
        )}
      </div>
      <ol className="flex flex-col gap-1">
        {listed.map((m) => (
          <li key={m.code}>
            <Link
              href={mapHref(m.code)}
              scroll={false}
              aria-current={m === current ? "true" : undefined}
              className={`block rounded-lg border px-3 py-2.5 ${m === current ? "border-gold/50 bg-gold/5" : "border-transparent hover:bg-surface-hover/40"}`}
            >
              <span className="flex items-baseline justify-between gap-3">
                <span className="truncate text-sm font-semibold text-foreground">{m.title ?? m.code}</span>
                <span className="shrink-0 text-xs tabular-nums text-text-muted">
                  {kd(m.kills, m.deaths)} K/D
                </span>
              </span>
              <span className="mt-1.5 block h-1 overflow-hidden rounded-full bg-border">
                <span
                  className="block h-full rounded-full bg-gold/80"
                  style={{ width: `${Math.max(((m.kills + m.deaths) / busiest) * 100, 2)}%` }}
                />
              </span>
              <span className="mt-1 block text-[11px] tabular-nums text-text-dim">
                {m.matches} match{m.matches === 1 ? "" : "es"} · {m.kills} kills · {m.deaths} deaths
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Career marks in the shape the map draws: a kill is a gold dot where the player stood. */
function plotted(marks: RecordMark[]): { kills: KillMark[]; deaths: DeathMark[] } {
  const kills: KillMark[] = [];
  const deaths: DeathMark[] = [];
  marks.forEach((m, seq) => {
    const at: [number, number, number] = [m.x, m.y, m.z];
    const weapon = weaponName(m.weapon);
    const how = [weapon, m.headshot ? "headshot" : null].filter(Boolean).join(", ");
    const tail = how ? ` (${how})` : "";
    if (m.kind === "kill") {
      kills.push({ seq, t_ms: 0, from: at, to: at, alone: true, label: `Killed ${m.other ?? "someone"}${tail}` });
    } else {
      deaths.push({ seq, t_ms: 0, at, label: `Killed by ${m.other ?? "someone"}${tail}` });
    }
  });
  return { kills, deaths };
}

function Arsenal({ record, shares }: { record: PlayerRecord; shares: ReturnType<typeof styleShares> }) {
  const top = record.weapons[0]?.kills ?? 1;
  return (
    <div>
      <div className="flex h-3 gap-[2px] overflow-hidden rounded-sm" role="img" aria-label={shares.map((s) => `${WEAPON_CLASSES[s.key].label} ${Math.round(s.share * 100)}%`).join(", ")}>
        {shares.map((s) => (
          <span key={s.key} title={WEAPON_CLASSES[s.key].label} style={{ flexGrow: s.share, background: WEAPON_CLASSES[s.key].colour }} />
        ))}
      </div>
      <ul className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        {shares.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-2 rounded-sm" style={{ background: WEAPON_CLASSES[s.key].colour }} />
            {WEAPON_CLASSES[s.key].label} <span className="tabular-nums text-foreground">{Math.round(s.share * 100)}%</span>
          </li>
        ))}
      </ul>
      <ol className="mt-6 space-y-3">
        {record.weapons.slice(0, 7).map((w) => (
          <li key={w.weapon}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="truncate text-foreground">{weaponName(w.weapon)}</span>
              <span className="shrink-0 tabular-nums text-text-muted">
                {w.headshots > 0 && <span className="mr-3 text-xs text-text-dim">{Math.round((w.headshots / w.kills) * 100)}% headshots</span>}
                <span className="font-semibold text-foreground">{w.kills}</span>
              </span>
            </div>
            <div className="mt-1 h-1 rounded-full bg-border">
              <div className="h-full rounded-full bg-gold" style={{ width: `${(w.kills / top) * 100}%` }} />
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Rivals({ rivals }: { rivals: RecordRival[] }) {
  const peak = Math.max(...rivals.flatMap((r) => [r.kills, r.deaths]), 1);
  const nemesis = rivals.reduce((a, b) => (b.deaths > a.deaths ? b : a));
  const prey = rivals.reduce((a, b) => (b.kills > a.kills ? b : a));
  return (
    <div>
      <p className="mb-4 flex justify-between text-xs text-text-muted">
        <span>Kills on them</span>
        <span>Their kills</span>
      </p>
      <ol className="space-y-4">
        {rivals.map((r) => (
          <li key={r.user?.id ?? r.name}>
            <div className="flex items-center gap-2.5">
              <PlayerAvatar name={r.name} user={r.user} size="sm" />
              <Link href={playerHref(r)} className="min-w-0 truncate text-sm font-semibold text-foreground hover:text-gold">{r.name}</Link>
              {r === nemesis && r.deaths > 0 && <Tag>Nemesis</Tag>}
              {r === prey && r !== nemesis && r.kills > 0 && <Tag>Favourite target</Tag>}
            </div>
            <div className="mt-1.5 grid grid-cols-[2.25rem_1fr_1fr_2.25rem] items-center gap-[3px] text-sm font-semibold tabular-nums">
              <span className="text-foreground">{r.kills}</span>
              <span className="flex h-1.5 justify-end rounded-l-full bg-border/60">
                <span className="rounded-l-full bg-gold" style={{ width: `${(r.kills / peak) * 100}%` }} />
              </span>
              <span className="flex h-1.5 rounded-r-full bg-border/60">
                <span className="rounded-r-full bg-accent-red/80" style={{ width: `${(r.deaths / peak) * 100}%` }} />
              </span>
              <span className="text-right text-foreground">{r.deaths}</span>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Tag({ children }: { children: ReactNode }) {
  return <span className="shrink-0 rounded-sm border border-border-bright px-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">{children}</span>;
}

const TIER_RING = { bronze: "text-bronze", silver: "text-silver", gold: "text-gold" } as const;

function MedalCase({ medals }: { medals: Record<string, number> }) {
  const earned = MEDALS.filter((m) => medals[m.type]);
  return (
    <div>
      <p className="mb-5 text-sm text-text-muted">
        {earned.length} of {MEDALS.length} kinds earned.
      </p>
      <ul className="grid grid-cols-3 gap-x-3 gap-y-6 sm:grid-cols-5 lg:grid-cols-10">
        {MEDALS.map((m) => (
          <Medal key={m.type} medal={m} count={medals[m.type] ?? 0} />
        ))}
      </ul>
    </div>
  );
}

/** A medal: a notched disc in its tier's colour, cast dark until it is earned. */
function Medal({ medal, count }: { medal: MedalInfo; count: number }) {
  const Icon = medal.icon;
  const earned = count > 0;
  return (
    <li className="flex flex-col items-center text-center" title={`${medal.name}: ${medal.what}`}>
      <span className={`relative flex h-16 w-16 items-center justify-center ${earned ? TIER_RING[medal.tier] : "text-border-bright"}`}>
        <svg viewBox="0 0 64 64" aria-hidden className="absolute inset-0 h-full w-full">
          <circle cx="32" cy="32" r="29" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="10.2 3.46" opacity={earned ? 0.9 : 0.5} />
          <circle cx="32" cy="32" r="23" fill="currentColor" opacity={earned ? 0.14 : 0.04} />
        </svg>
        {medal.mark ? (
          <span className="record-display relative text-2xl leading-none">{medal.mark}</span>
        ) : (
          Icon && <Icon aria-hidden className="relative h-6 w-6" strokeWidth={1.75} />
        )}
      </span>
      <span className={`mt-2 text-xs leading-tight ${earned ? "text-foreground" : "text-text-dim"}`}>{medal.name}</span>
      <span className={`text-xs tabular-nums ${earned ? "text-text-muted" : "text-text-dim"}`}>{earned ? `×${count}` : "–"}</span>
    </li>
  );
}
