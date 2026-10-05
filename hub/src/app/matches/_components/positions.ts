import type { MatchEvent } from "@/lib/api/matches";
import { duration, eventLine } from "./format";

/** Unreal world space, centimetres, Z up. */
export type Point = [number, number, number];

/** A kill: the killer's position (none for a suicide or no report) and the victim's. */
export type KillMark = { seq: number; from: Point | null; to: Point; label: string };
/** A death no kill accounts for: falls, suicides, the guardians. */
export type DeathMark = { seq: number; at: Point; label: string };

/**
 * The kills and deaths a position plot draws, with the line each dot's
 * hover shows. With `focus`, only that player's. Plain data, so the server
 * can hand it to the map's client component.
 */
export function positionMarks(
  events: MatchEvent[],
  nameOf: (index: number) => string,
  focus: number | null,
): { kills: KillMark[]; deaths: DeathMark[] } {
  const killed = new Set(
    events.filter((e) => e.type === "kill").map((e) => `${e.effect}:${Math.round(e.t_ms / 1000)}`),
  );
  const label = (e: MatchEvent) => `${duration(e.t_ms)}  ${eventLine(e, nameOf) ?? `${nameOf(e.effect)} died`}`;
  const kills = events
    .filter((e) => e.type === "kill" && e.effect_pos && (focus === null || e.cause === focus || e.effect === focus))
    .map((e) => ({
      seq: e.seq,
      from: e.cause_pos && e.cause !== e.effect ? e.cause_pos : null,
      to: e.effect_pos!,
      label: label(e),
    }));
  const deaths = events
    .filter(
      (e) =>
        e.type === "death" &&
        e.effect_pos &&
        (focus === null || e.effect === focus) &&
        !killed.has(`${e.effect}:${Math.round(e.t_ms / 1000)}`),
    )
    .map((e) => ({ seq: e.seq, at: e.effect_pos!, label: label(e) }));
  return { kills, deaths };
}
