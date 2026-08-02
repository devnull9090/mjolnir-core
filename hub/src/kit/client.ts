/**
 * One typed client for the whole hub API, shared by the website and the
 * launcher.
 *
 * The transport is injectable because the two callers reach the API very
 * differently. In the browser it is same-origin `fetch` with the session
 * cookie. In the launcher the webview cannot hold a hub cookie and should
 * not hold an API key either, so requests go through a Tauri command that
 * attaches the paired key in Rust — the key never enters the webview.
 * Everything above the transport (paths, query building, error shapes) is
 * written once, here.
 */
import type {
  Comment,
  ConflictPair,
  DevicePoll,
  DeviceStart,
  Media,
  ModDetail,
  ModList,
  ModListQuery,
  RatingSummary,
  Release,
  ReleaseStatusDetail,
  ReportReason,
  ReportSubject,
  User,
} from "./types";

export interface HubRequest {
  method: "GET" | "POST" | "PUT" | "DELETE";
  /** API path below the version prefix, e.g. `/mods/my-pack/ratings`. */
  path: string;
  query?: Record<string, string | number | undefined>;
  body?: unknown;
}

export interface HubResponse {
  status: number;
  /** Parsed JSON body, or null for empty/non-JSON responses. */
  body: unknown;
}

export type HubTransport = (req: HubRequest) => Promise<HubResponse>;

/** A non-2xx answer, carrying whatever the API's Error shape said. */
export class HubError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "HubError";
  }

  /** True when signing in would plausibly fix it. */
  get needsAuth(): boolean {
    return this.status === 401 || this.status === 403;
  }
}

export interface HubClientOptions {
  /**
   * Origin the API lives on, no trailing slash. Empty string means
   * same-origin, which is what the website wants.
   */
  baseUrl?: string;
  /** Bearer key (`mjc_…`) for non-browser callers that hold one directly. */
  token?: string;
  /** Overrides everything above; used by the launcher's Tauri transport. */
  transport?: HubTransport;
  fetchImpl?: typeof fetch;
}

const PREFIX = "/api/v1";

function buildPath(req: HubRequest): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(req.query ?? {})) {
    if (v !== undefined && v !== "") q.set(k, String(v));
  }
  const qs = q.toString();
  return `${PREFIX}${req.path}${qs ? `?${qs}` : ""}`;
}

function fetchTransport(options: HubClientOptions): HubTransport {
  const doFetch = options.fetchImpl ?? globalThis.fetch;
  return async (req) => {
    const headers: Record<string, string> = {};
    if (req.body !== undefined) headers["Content-Type"] = "application/json";
    if (options.token) headers["Authorization"] = `Bearer ${options.token}`;

    const res = await doFetch(`${options.baseUrl ?? ""}${buildPath(req)}`, {
      method: req.method,
      headers,
      body: req.body === undefined ? undefined : JSON.stringify(req.body),
      // Cookie sessions are the website's whole auth story.
      credentials: options.token ? "omit" : "include",
    });
    const text = await res.text();
    let body: unknown = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = null;
    }
    return { status: res.status, body };
  };
}

export class HubClient {
  private readonly transport: HubTransport;

  constructor(private readonly options: HubClientOptions = {}) {
    this.transport = options.transport ?? fetchTransport(options);
  }

  /** Absolute URL for a hub-relative path, for <img src> and browser links. */
  absolute(path: string): string {
    if (/^https?:\/\//.test(path)) return path;
    return `${this.options.baseUrl ?? ""}${path}`;
  }

  private async call<T>(req: HubRequest): Promise<T> {
    const res = await this.transport(req);
    if (res.status < 200 || res.status >= 300) {
      const err = (res.body ?? {}) as { error?: string; message?: string };
      throw new HubError(
        res.status,
        err.error ?? "http_error",
        err.message ?? err.error ?? `Hub returned ${res.status}`,
      );
    }
    return res.body as T;
  }

  // ── Mods ────────────────────────────────────────────────────────────

  listMods(query: ModListQuery = {}): Promise<ModList> {
    return this.call({ method: "GET", path: "/mods", query: { ...query } });
  }

  getMod(slug: string): Promise<ModDetail> {
    return this.call({ method: "GET", path: `/mods/${encodeURIComponent(slug)}` });
  }

  async listReleases(slug: string): Promise<Release[]> {
    const r = await this.call<{ releases: Release[] }>({
      method: "GET",
      path: `/mods/${encodeURIComponent(slug)}/releases`,
    });
    return r.releases;
  }

  getRelease(id: string): Promise<ReleaseStatusDetail> {
    return this.call({ method: "GET", path: `/releases/${encodeURIComponent(id)}` });
  }

  releaseDownloadUrl(id: string): string {
    return this.absolute(`${PREFIX}/releases/${encodeURIComponent(id)}/download`);
  }

  async listMedia(slug: string): Promise<Media[]> {
    const r = await this.call<{ media: Media[] }>({
      method: "GET",
      path: `/mods/${encodeURIComponent(slug)}/media`,
    });
    return r.media;
  }

  // ── Ratings & comments ──────────────────────────────────────────────

  getRatings(slug: string): Promise<RatingSummary> {
    return this.call({ method: "GET", path: `/mods/${encodeURIComponent(slug)}/ratings` });
  }

  putRating(slug: string, score: number, reviewMd?: string): Promise<{ ok: boolean }> {
    return this.call({
      method: "PUT",
      path: `/mods/${encodeURIComponent(slug)}/ratings/me`,
      body: { score, review_md: reviewMd || undefined },
    });
  }

  async listComments(slug: string): Promise<Comment[]> {
    const r = await this.call<{ comments: Comment[] }>({
      method: "GET",
      path: `/mods/${encodeURIComponent(slug)}/comments`,
    });
    return r.comments;
  }

  postComment(slug: string, bodyMd: string, parentId?: string): Promise<{ id: string }> {
    return this.call({
      method: "POST",
      path: `/mods/${encodeURIComponent(slug)}/comments`,
      body: { body_md: bodyMd, parent_id: parentId },
    });
  }

  deleteComment(id: string): Promise<{ ok: boolean }> {
    return this.call({ method: "DELETE", path: `/comments/${encodeURIComponent(id)}` });
  }

  // ── Conflicts ───────────────────────────────────────────────────────

  async checkConflicts(releaseIds: string[]): Promise<ConflictPair[]> {
    if (releaseIds.length < 2) return [];
    const r = await this.call<{ pairs: ConflictPair[] }>({
      method: "POST",
      path: "/conflicts/check",
      body: { release_ids: releaseIds },
    });
    return r.pairs;
  }

  // ── Moderation ──────────────────────────────────────────────────────

  reportContent(
    subjectType: ReportSubject,
    subjectId: string,
    reason: ReportReason,
    detail?: string,
  ): Promise<{ id: string }> {
    return this.call({
      method: "POST",
      path: "/reports",
      body: { subject_type: subjectType, subject_id: subjectId, reason, detail: detail || undefined },
    });
  }

  // ── Identity ────────────────────────────────────────────────────────

  /** The signed-in user, or null when the caller is anonymous. */
  async me(): Promise<User | null> {
    try {
      return await this.call<User>({ method: "GET", path: "/auth/me" });
    } catch (e) {
      if (e instanceof HubError && e.status === 401) return null;
      throw e;
    }
  }

  logout(): Promise<{ ok: boolean }> {
    return this.call({ method: "POST", path: "/auth/logout" });
  }

  /** Sign-in URL for a browser; `next` returns the user to where they were. */
  signInUrl(next = "/"): string {
    return this.absolute(`${PREFIX}/auth/discord?next=${encodeURIComponent(next)}`);
  }

  // ── Device pairing (desktop clients) ────────────────────────────────

  startDevicePairing(clientName: string): Promise<DeviceStart> {
    return this.call({ method: "POST", path: "/auth/device/start", body: { client_name: clientName } });
  }

  pollDevicePairing(deviceCode: string): Promise<DevicePoll> {
    return this.call({ method: "POST", path: "/auth/device/token", body: { device_code: deviceCode } });
  }

  approveDevicePairing(userCode: string, approve: boolean): Promise<{ status: string }> {
    return this.call({
      method: "POST",
      path: "/auth/device/approve",
      body: { user_code: userCode, approve },
    });
  }
}

export function createHubClient(options: HubClientOptions = {}): HubClient {
  return new HubClient(options);
}
