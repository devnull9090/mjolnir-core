/**
 * One map as a tile: its cover, what it plays, and where it stands on this
 * machine. Multiplayer (the classics) and Browse Hub's Maps tab (everything)
 * both draw maps with this, so the two screens cannot disagree about whether
 * a map is installed or out of date.
 */
import type { ReactNode } from "react";
import { GAME_TYPE_NAMES, type MapListing } from "@mjolnir/hub-kit";

import { HUB_SITE } from "../../hub/client";
import { isNewerVersion, type InstalledMod } from "../../hub/library";

export type MapStatus = "installed" | "update" | "missing-files" | "not-installed";

/**
 * Where one map stands against the hub. "Update" is decided by version, the
 * way `hub_check_updates` decides it for the Updates tab, not by release id:
 * the two screens must agree, and a re-published release of the same version
 * is not something to download again.
 */
export function mapStatus(
  listing: MapListing,
  have: InstalledMod | undefined,
  filesGone: boolean,
): MapStatus {
  if (!have) return "not-installed";
  if (filesGone) return "missing-files";
  if (listing.release && isNewerVersion(listing.release.version, have.version)) return "update";
  return "installed";
}

/** Which game a map comes from, as the hub's `game` field says. */
export type MapGame = "halo1" | "halo2";

const GAME_NAMES: Record<MapGame, string> = { halo1: "Halo CE", halo2: "Halo 2" };

/**
 * The listing's `game`, or null where it has none: hubs from before the
 * field send nothing, and those listings are CE maps.
 */
export function mapGame(listing: MapListing): MapGame | null {
  const game: string | null | undefined = listing.game;
  return game === "halo1" || game === "halo2" ? game : null;
}

/** A CE map: tagged `halo1`, or untagged (listed before the field). */
export function isHaloCeMap(listing: MapListing): boolean {
  const game: string | null | undefined = listing.game;
  return game == null || game === "halo1";
}

const BADGE: Record<MapStatus, { label: string; className: string }> = {
  installed: { label: "Installed", className: "bg-surface-primary/85 text-emerald-400 border-emerald-400/35" },
  update: { label: "Update", className: "bg-surface-primary/85 text-mjolnir-gold border-mjolnir-gold/45" },
  "missing-files": { label: "Files missing", className: "bg-surface-primary/85 text-red-400 border-red-400/40" },
  "not-installed": { label: "Not installed", className: "bg-surface-primary/85 text-text-secondary border-white/10" },
};

function versionTitle(
  status: MapStatus,
  have: InstalledMod | undefined,
  latest: string | undefined,
): string | undefined {
  switch (status) {
    case "installed":
      return `Installed v${have?.version}, the newest on the hub`;
    case "update":
      return `Installed v${have?.version}; v${latest} is on the hub`;
    case "missing-files":
      return `v${have?.version} was installed but its files are gone; Install puts them back`;
    case "not-installed":
      return latest ? `v${latest} is on the hub` : undefined;
  }
}

/** "Halo 2 · Large · 8–16 players · Vehicles", from whatever the listing knows. */
function facts(m: MapListing): string[] {
  const out: string[] = [];
  const game = mapGame(m);
  if (game) out.push(GAME_NAMES[game]);
  if (m.size) out.push(m.size[0].toUpperCase() + m.size.slice(1));
  if (m.players_min && m.players_max) {
    out.push(
      m.players_min === m.players_max
        ? `${m.players_max} players`
        : `${m.players_min}–${m.players_max} players`,
    );
  } else if (m.players_max) {
    out.push(`Up to ${m.players_max}`);
  }
  if (m.vehicles === true) out.push("Vehicles");
  if (m.vehicles === false) out.push("On foot");
  return out;
}

export function MapTile({
  map,
  have,
  status,
  onSelect,
  action,
  showOwner = false,
}: {
  map: MapListing;
  have: InstalledMod | undefined;
  status: MapStatus;
  /** Opens the map's full page (gallery, releases, ratings). */
  onSelect?: () => void;
  /** Install / Update, under the facts line. */
  action?: ReactNode;
  /** Community maps name their author; the classics do not need to. */
  showOwner?: boolean;
}) {
  const latest = map.release?.version;
  const details = facts(map);
  const cover = (
    <div className="relative w-full aspect-video overflow-hidden bg-surface-hover">
      {map.cover_url ? (
        <img
          src={map.cover_url.startsWith("/") ? `${HUB_SITE}${map.cover_url}` : map.cover_url}
          alt={map.title}
          loading="lazy"
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105 motion-reduce:transition-none motion-reduce:group-hover:scale-100"
        />
      ) : (
        <div className="w-full h-full bg-gradient-to-br from-surface-card to-surface-primary flex items-center justify-center">
          <span className="font-mono text-2xl font-bold tracking-widest text-text-secondary/40">
            {map.code}
          </span>
        </div>
      )}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-surface-secondary/80 to-transparent"
      />
      <span className="absolute left-2.5 top-2.5 rounded bg-surface-primary/80 px-1.5 py-0.5 font-mono text-[10px] font-bold tracking-wider text-text-secondary backdrop-blur-sm border border-white/10">
        {map.code}
      </span>
      <span
        className={`absolute right-2.5 top-2.5 text-[10px] font-semibold px-2 py-0.5 rounded-full backdrop-blur-sm border border-white/10 ${BADGE[status].className}`}
      >
        {BADGE[status].label}
      </span>
    </div>
  );

  return (
    <div
      className={`group launcher-card bg-surface-secondary border border-border-subtle rounded-xl overflow-hidden flex flex-col ${
        onSelect ? "hover:border-mjolnir-gold/45" : ""
      }`}
    >
      {onSelect ? (
        <button
          type="button"
          onClick={onSelect}
          className="block text-left cursor-pointer w-full"
          title={`Open ${map.title}`}
        >
          {cover}
        </button>
      ) : (
        cover
      )}
      <div className="p-3.5 flex-1 flex flex-col">
        <div className="flex items-center justify-between gap-2">
          {onSelect ? (
            <button
              type="button"
              onClick={onSelect}
              className="font-bold text-sm truncate text-left transition-colors group-hover:text-mjolnir-gold cursor-pointer"
            >
              {map.title}
            </button>
          ) : (
            <span className="font-bold text-sm truncate">{map.title}</span>
          )}
          <span
            className="shrink-0 text-[11px] font-mono text-text-secondary tabular-nums"
            title={versionTitle(status, have, latest)}
          >
            {status === "update" && have && latest ? (
              <>
                v{have.version} <span className="text-mjolnir-gold">→ v{latest}</span>
              </>
            ) : have ? (
              `v${have.version}`
            ) : latest ? (
              `v${latest}`
            ) : null}
          </span>
        </div>
        <p className="mt-1 text-xs text-text-secondary truncate">
          {map.modes.map((mode) => GAME_TYPE_NAMES[mode] ?? mode).join(" · ")}
        </p>
        {(details.length > 0 || showOwner) && (
          <div className="flex items-center justify-between gap-2 mt-1 text-[11px] text-text-secondary/80">
            <span className="truncate">{details.join(" · ")}</span>
            {showOwner && <span className="truncate shrink-0 max-w-[45%]">by {map.owner}</span>}
          </div>
        )}
        {action && <div className="mt-3 pt-2.5 border-t border-border-subtle/50 flex items-center gap-2">{action}</div>}
      </div>
    </div>
  );
}
