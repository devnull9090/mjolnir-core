/**
 * Browsing maps: the classics and the community's, searched and filtered by
 * what a map plays like rather than by a mod category.
 *
 * Nothing here installs on its own. Install multiplayer (the Multiplayer
 * view) brings the official classics; every other map is one Install
 * button here, or a download in game when a lobby needs it.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  ActionButton,
  ErrorNote,
  GAME_TYPE_NAMES,
  SearchIcon,
  Spinner,
  useHub,
  type MapListing,
  type MapQuery,
} from "@mjolnir/hub-kit";

import type { Library } from "../../hub/library";
import { MapTile, mapStatus } from "./MapTile";

type Source = "all" | "official" | "community";
type Size = "any" | NonNullable<MapQuery["size"]>;
type Vehicles = "any" | "yes" | "no";
type Sort = NonNullable<MapQuery["sort"]>;

const SOURCES: { key: Source; label: string }[] = [
  { key: "all", label: "All maps" },
  { key: "official", label: "Classics" },
  { key: "community", label: "Community" },
];

const SORTS: { key: Sort; label: string }[] = [
  { key: "newest", label: "Newest" },
  { key: "downloads", label: "Downloads" },
  { key: "rating", label: "Top rated" },
  { key: "title", label: "A–Z" },
];

const MODES = ["all", ...Object.keys(GAME_TYPE_NAMES)];
const SIZES: Size[] = ["any", "small", "medium", "large"];
const PLAYERS = [0, 2, 4, 8, 12, 16];

const PAGE = 24;

function chip(active: boolean) {
  return `px-2.5 py-1 rounded-lg border text-xs transition-colors cursor-pointer ${
    active
      ? "border-mjolnir-gold/60 text-mjolnir-gold"
      : "border-border-subtle text-text-secondary hover:text-text-primary"
  }`;
}

export function MapBrowser({
  library,
  onSelect,
}: {
  library: Library;
  onSelect: (slug: string) => void;
}) {
  const { client } = useHub();
  const [maps, setMaps] = useState<MapListing[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [source, setSource] = useState<Source>("all");
  const [mode, setMode] = useState("all");
  const [size, setSize] = useState<Size>("any");
  const [vehicles, setVehicles] = useState<Vehicles>("any");
  const [players, setPlayers] = useState(0);
  const [sort, setSort] = useState<Sort>("newest");
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);

  const filters = useMemo<MapQuery>(
    () => ({
      q: debounced || undefined,
      official: source === "all" ? undefined : source === "official",
      mode: mode === "all" ? undefined : mode,
      size: size === "any" ? undefined : size,
      vehicles: vehicles === "any" ? undefined : vehicles === "yes",
      players: players || undefined,
      sort,
      limit: PAGE,
    }),
    [debounced, source, mode, size, vehicles, players, sort],
  );

  // Guards against a slow first page landing after the filters moved on.
  const generation = useRef(0);

  const load = useCallback(
    async (append: boolean, after: string | null) => {
      const mine = ++generation.current;
      setLoading(true);
      try {
        const page = await client.searchMaps({ ...filters, cursor: after ?? undefined });
        if (mine !== generation.current) return;
        setMaps((prev) => (append ? [...prev, ...page.maps] : page.maps));
        setCursor(page.next_cursor);
        setOffline(null);
      } catch (e) {
        if (mine !== generation.current) return;
        setOffline(e instanceof Error ? e.message : String(e));
      } finally {
        if (mine === generation.current) setLoading(false);
      }
    },
    [client, filters],
  );

  useEffect(() => {
    void load(false, null);
  }, [load]);

  // As on the Multiplayer view: a map whose files were deleted by hand reads
  // as needing an install, not as installed.
  const [missingFiles, setMissingFiles] = useState<Set<string>>(new Set());
  useEffect(() => {
    invoke<string[]>("hub_missing_files").then(
      (slugs) => setMissingFiles(new Set(slugs)),
      () => setMissingFiles(new Set()),
    );
  }, [library.state]);

  const installedBySlug = new Map((library.state?.installed ?? []).map((m) => [m.slug, m]));

  const action = (m: MapListing) => {
    const status = mapStatus(m, installedBySlug.get(m.slug), missingFiles.has(m.slug));
    if (status === "installed" || !m.release) return null;
    const busy = library.busy === m.slug;
    const label =
      status === "update"
        ? busy
          ? "Updating…"
          : `Update → ${m.release.version}`
        : busy
          ? "Installing…"
          : "Install";
    return (
      <ActionButton
        onClick={() =>
          void library.run(m.slug, "hub_install", {
            slug: m.slug,
            releaseId: status === "update" ? m.release?.id : undefined,
          })
        }
        disabled={!!library.busy}
        title={
          m.release.file_size
            ? `About ${(m.release.file_size / 1_048_576).toFixed(0)} MB, plus anything it needs`
            : undefined
        }
      >
        {busy ? <Spinner className="w-3.5 h-3.5" /> : null}
        {label}
      </ActionButton>
    );
  };

  const filtered =
    !!debounced || source !== "all" || mode !== "all" || size !== "any" || vehicles !== "any" || !!players;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-52">
          <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search maps by name or code…"
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg bg-surface-secondary border border-border-subtle focus:border-mjolnir-gold/60 focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-1 text-xs">
          {SORTS.map((s) => (
            <button
              key={s.key}
              onClick={() => setSort(s.key)}
              className={`px-3 py-1.5 rounded-lg border transition-colors cursor-pointer ${
                sort === s.key
                  ? "border-mjolnir-gold/60 text-mjolnir-gold"
                  : "border-border-subtle text-text-secondary hover:text-text-primary"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-1">
          {SOURCES.map((s) => (
            <button key={s.key} onClick={() => setSource(s.key)} className={chip(source === s.key)}>
              {s.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {MODES.map((m) => (
            <button key={m} onClick={() => setMode(m)} className={chip(mode === m)}>
              {m === "all" ? "Any game type" : (GAME_TYPE_NAMES[m] ?? m)}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-1">
          {SIZES.map((s) => (
            <button key={s} onClick={() => setSize(s)} className={`${chip(size === s)} capitalize`}>
              {s === "any" ? "Any size" : s}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {(["any", "yes", "no"] as Vehicles[]).map((v) => (
            <button key={v} onClick={() => setVehicles(v)} className={chip(vehicles === v)}>
              {v === "any" ? "Vehicles or not" : v === "yes" ? "Vehicles" : "On foot"}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs text-text-secondary">
          Players
          <select
            value={players}
            onChange={(e) => setPlayers(Number(e.target.value))}
            className="px-2 py-1 rounded-lg bg-surface-secondary border border-border-subtle text-text-primary focus:border-mjolnir-gold/60 focus:outline-none"
          >
            {PLAYERS.map((n) => (
              <option key={n} value={n}>
                {n === 0 ? "Any" : `Fits ${n}`}
              </option>
            ))}
          </select>
        </label>
      </div>

      {offline && (
        <ErrorNote>
          Could not reach the hub ({offline}). Installed maps keep working offline.
        </ErrorNote>
      )}

      <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">
        {maps.map((m) => (
          <MapTile
            key={m.code}
            map={m}
            have={installedBySlug.get(m.slug)}
            status={mapStatus(m, installedBySlug.get(m.slug), missingFiles.has(m.slug))}
            onSelect={() => onSelect(m.slug)}
            action={action(m)}
            showOwner={!m.official}
          />
        ))}
      </div>

      {loading && (
        <p className="flex items-center gap-2 text-sm text-text-secondary">
          <Spinner /> Loading…
        </p>
      )}
      {!loading && maps.length === 0 && !offline && (
        <p className="text-sm text-text-secondary">
          {filtered ? "No maps match those filters." : "No maps are published yet."}
        </p>
      )}
      {cursor && !loading && (
        <ActionButton tone="neutral" onClick={() => void load(true, cursor)}>
          Load more
        </ActionButton>
      )}
    </div>
  );
}
