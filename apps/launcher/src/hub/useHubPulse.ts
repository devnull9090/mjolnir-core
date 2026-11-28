/**
 * Live hub telemetry for the launcher: open public lobbies, recent completed
 * matches, newest community mods, and map cover URLs.
 *
 * Kept in one hook at the app root so Home, Multiplayer, Header and Sidebar
 * read the same live state without repeating hub requests. Fails silently when
 * offline so local mod management and game launch are never disturbed.
 */
import { useCallback, useEffect, useState } from "react";
import type { Lobby, MapListing, MatchSummary, Mod } from "@mjolnir/hub-kit";

import { hubClient } from "./client";

export interface HubPulse {
  lobbies: Lobby[];
  livePlayers: number;
  matches: MatchSummary[];
  latestMods: Mod[];
  maps: MapListing[];
  coversByCode: Map<string, string | null>;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const POLL_MS = 30_000;

export function useHubPulse(): HubPulse {
  const [lobbies, setLobbies] = useState<Lobby[]>([]);
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [latestMods, setLatestMods] = useState<Mod[]>([]);
  const [maps, setMaps] = useState<MapListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (isInitial: boolean) => {
    if (isInitial) setLoading(true);
    else setRefreshing(true);
    try {
      const [lobbiesRes, matchesRes, modsRes, mapsRes] = await Promise.allSettled([
        hubClient.listLobbies(),
        hubClient.listMatches({ real: true, limit: 4 }),
        hubClient.listMods({ type: "content", map: false, sort: "newest", limit: 4 }),
        hubClient.listMaps(),
      ]);

      let anySucceeded = false;
      if (lobbiesRes.status === "fulfilled") {
        setLobbies(lobbiesRes.value);
        anySucceeded = true;
      }
      if (matchesRes.status === "fulfilled") {
        setMatches(matchesRes.value.matches);
        anySucceeded = true;
      }
      if (modsRes.status === "fulfilled") {
        setLatestMods(modsRes.value.mods);
        anySucceeded = true;
      }
      if (mapsRes.status === "fulfilled") {
        setMaps(mapsRes.value);
        anySucceeded = true;
      }

      if (anySucceeded) {
        setError(null);
      } else {
        const firstErr = [lobbiesRes, matchesRes, modsRes, mapsRes].find(
          (r): r is PromiseRejectedResult => r.status === "rejected",
        );
        setError(firstErr ? String(firstErr.reason) : "Could not reach the hub.");
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load(true);
    // Gentle refresh for live lobbies while the launcher window is visible.
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") {
        hubClient
          .listLobbies()
          .then((next) => setLobbies(next))
          .catch(() => {});
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const coversByCode = new Map(maps.map((m) => [m.code, m.cover_url]));
  const livePlayers = lobbies.reduce((sum, l) => sum + l.players, 0);

  return {
    lobbies,
    livePlayers,
    matches,
    latestMods,
    maps,
    coversByCode,
    loading,
    refreshing,
    error,
    refresh: () => load(false),
  };
}
