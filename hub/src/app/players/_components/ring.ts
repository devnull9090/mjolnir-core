/**
 * The career signature's geometry, shared by the full ring on a record and
 * the small ones on the leaderboards' podium.
 */
import type { RecordMatch } from "@/lib/api/player-record";

export type Spoke = Pick<RecordMatch, "kills" | "deaths">;

export const SIZE = 640;
export const C = SIZE / 2;
/** The circle matches sit on: kills reach out from it, deaths in. */
export const BASE = 176;
export const OUT = 126;
export const IN = 74;
/** A spoke with nothing on one side still shows as a stub. */
const STUB = 3;

/** Rounded: server and browser differ in a float's last digits, and React compares them. */
export function point(angle: number, radius: number) {
  const round = (v: number) => Math.round(v * 100) / 100;
  return [round(C + radius * Math.sin(angle)), round(C - radius * Math.cos(angle))] as const;
}

export interface RingScale {
  step: number;
  peakKills: number;
  peakDeaths: number;
  width: number;
}

export function ringScale(matches: Spoke[], maxWidth = 10): RingScale {
  const step = (Math.PI * 2) / Math.max(matches.length, 1);
  return {
    step,
    peakKills: Math.max(...matches.map((m) => m.kills), 1),
    peakDeaths: Math.max(...matches.map((m) => m.deaths), 1),
    width: Math.max(1.6, Math.min(maxWidth, BASE * step * 0.62)),
  };
}

/** The two lines of the i-th spoke, as [x1, y1, x2, y2]. */
export function spokeEnds(m: Spoke, i: number, s: RingScale) {
  const angle = i * s.step + s.step / 2;
  return {
    kills: [...point(angle, BASE + 2), ...point(angle, BASE + 2 + Math.max((m.kills / s.peakKills) * OUT, STUB))],
    deaths: [...point(angle, BASE - 2), ...point(angle, BASE - 2 - Math.max((m.deaths / s.peakDeaths) * IN, STUB))],
  };
}
