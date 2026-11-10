/**
 * The medals of one match, per seat, from its recorded events. The same
 * rules as a player's medal case (lib/api/player-record.ts): only the
 * incidents counted as medals, and a medal the game sends together with one
 * that stands for it (a headshot beside a sniper headshot) counted once.
 */
import { MEDAL_HIDDEN_BY, MEDAL_TYPES } from "@/lib/api/player-record";
import type { MatchEvent } from "@/lib/api/matches";
import { MEDALS, type MedalInfo } from "../../players/_components/record";

/** A medal hidden by another counts as hidden when both came this close. */
const HIDDEN_MS = 500;
const TIER_WORTH = { gold: 3, silver: 2, bronze: 1 } as const;

export interface SeatMedal {
  medal: MedalInfo;
  count: number;
}

/** Seat index -> its medals, the rarest tier first, then the most earned. */
export function matchMedals(events: MatchEvent[]): Map<number, SeatMedal[]> {
  const counted = new Set<string>(MEDAL_TYPES);
  const info = new Map(MEDALS.map((m) => [m.type, m]));
  const medals = events.filter((e) => e.cause >= 0 && counted.has(e.type));
  const counts = new Map<number, Map<string, number>>();
  for (const e of medals) {
    const hiders = MEDAL_HIDDEN_BY[e.type];
    const hidden =
      hiders !== undefined &&
      medals.some((h) => h.cause === e.cause && hiders.includes(h.type) && Math.abs(h.t_ms - e.t_ms) <= HIDDEN_MS);
    if (hidden) continue;
    const seat = counts.get(e.cause) ?? new Map<string, number>();
    seat.set(e.type, (seat.get(e.type) ?? 0) + 1);
    counts.set(e.cause, seat);
  }
  const out = new Map<number, SeatMedal[]>();
  for (const [seat, byType] of counts) {
    const list: SeatMedal[] = [];
    for (const [type, count] of byType) {
      const medal = info.get(type);
      if (medal) list.push({ medal, count });
    }
    list.sort((a, b) => TIER_WORTH[b.medal.tier] - TIER_WORTH[a.medal.tier] || b.count - a.count);
    if (list.length) out.set(seat, list);
  }
  return out;
}

/** How many medals a seat earned in all. */
export function medalCount(list: SeatMedal[] | undefined): number {
  return (list ?? []).reduce((n, m) => n + m.count, 0);
}
