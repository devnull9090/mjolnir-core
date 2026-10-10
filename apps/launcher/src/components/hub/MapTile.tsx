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

const BADGE: Record<MapStatus, { label: string; className: string }> = {
  installed: { label: "Installed", className: "bg-emerald-500/15 text-emerald-400" },
  update: { label: "Update", className: "bg-mjolnir-gold/15 text-mjolnir-gold" },
  "missing-files": { label: "Files missing", className: "bg-red-500/15 text-red-400" },
  "not-installed": { label: "Not installed", className: "bg-surface-hover text-text-secondary" },
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

/** "Large · 8–16 players · Vehicles", from whatever the listing knows. */
function facts(m: MapListing): string[] {
  const out: string[] = [];
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
  const cover = map.cover_url ? (
    <img
      src={map.cover_url.startsWith("/") ? `${HUB_SITE}${map.cover_url}` : map.cover_url}
      alt={map.title}
      loading="lazy"
      className="w-full aspect-video object-cover bg-surface-hover"
    />
  ) : (
    <div className="w-full aspect-video bg-surface-hover flex items-center justify-center">
      <span className="font-mono text-2xl text-text-secondary/40">{map.code}</span>
    </div>
  );

  return (
    <div
      className={`bg-surface-secondary border border-border-subtle rounded-xl overflow-hidden flex flex-col ${
        onSelect ? "hover:border-mjolnir-gold/40 transition-colors" : ""
      }`}
    >
      {onSelect ? (
        <button
          type="button"
          onClick={onSelect}
          className="block text-left cursor-pointer"
          title={`Open ${map.title}`}
        >
          {cover}
        </button>
      ) : (
        cover
      )}
      <div className="p-3 flex-1 flex flex-col">
        <div className="flex items-center justify-between gap-2">
          {onSelect ? (
            <button
              type="button"
              onClick={onSelect}
              className="font-semibold truncate text-left hover:text-mjolnir-gold cursor-pointer"
            >
              {map.title}
            </button>
          ) : (
            <span className="font-semibold truncate">{map.title}</span>
          )}
          <span
            className={`text-[11px] px-1.5 py-0.5 rounded shrink-0 ${BADGE[status].className}`}
          >
            {BADGE[status].label}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2 mt-1 text-xs text-text-secondary">
          <span className="truncate">
            {map.modes.map((mode) => GAME_TYPE_NAMES[mode] ?? mode).join(" · ")}
          </span>
          <span className="shrink-0 tabular-nums" title={versionTitle(status, have, latest)}>
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
        {(details.length > 0 || showOwner) && (
          <div className="flex items-center justify-between gap-2 mt-1 text-xs text-text-secondary/80">
            <span className="truncate">{details.join(" · ")}</span>
            {showOwner && <span className="truncate shrink-0 max-w-[45%]">by {map.owner}</span>}
          </div>
        )}
        {action && <div className="mt-3 flex items-center gap-2">{action}</div>}
      </div>
    </div>
  );
}
