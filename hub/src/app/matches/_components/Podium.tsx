import Link from "next/link";

import type { MatchPlayer } from "@/lib/api/matches";
import { PlaceBadge, PlayerAvatar, TeamDot } from "../../components/ui";
import { kd, playerHref } from "./format";
import { MatchStats } from "./MatchStats";

const STEP = {
  1: "md:order-2 md:pt-0 border-gold/50 bg-gradient-to-b from-gold/20 to-surface",
  2: "md:order-1 md:mt-8 border-silver/40 bg-gradient-to-b from-silver/15 to-surface",
  3: "md:order-3 md:mt-14 border-bronze/40 bg-gradient-to-b from-bronze/15 to-surface",
} as const;

/**
 * The top three on steps: first in the middle and highest, second to its
 * left, third to its right. On a phone they stack in order, first on top,
 * which is also the order a screen reader reads them.
 */
export function Podium({ players }: { players: MatchPlayer[] }) {
  const top = players.filter((p) => p.place >= 1 && p.place <= 3).slice(0, 3);
  if (top.length < 2 || top.every((p) => p.score === 0)) return null;
  return (
    <ol aria-label="Podium" className="grid grid-cols-1 gap-3 md:grid-cols-3 md:items-start">
      {top.map((p) => {
        const place = p.place as 1 | 2 | 3;
        return (
          <li key={p.index} className={`rounded-2xl border p-5 text-center ${STEP[place]}`}>
            <Link href={playerHref(p)} className="group flex flex-col items-center gap-3">
              <PlayerAvatar name={p.name} user={p.user} size={place === 1 ? "xl" : "lg"} ring={place} />
              <PlaceBadge place={place} size="md" />
              <span className="max-w-full truncate text-lg font-bold text-foreground group-hover:text-gold">
                {p.name}
              </span>
            </Link>
            <div className="mt-1 flex items-center justify-center gap-2 text-xs text-text-muted">
              <TeamDot team={p.team} label />
              {p.user && <span>@{p.user.name}</span>}
            </div>
            <MatchStats
              className="mt-4"
              items={[
                ["Score", p.score],
                ["Kills", p.kills],
                ["K/D", kd(p.kills, p.deaths)],
              ]}
            />
          </li>
        );
      })}
    </ol>
  );
}
