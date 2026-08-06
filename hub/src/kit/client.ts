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
  MediaOwner,
  MediaStatus,
  ModDetail,
  ModList,
  ModListQuery,
  QueuedMedia,
  RatingSummary,
  Release,
  ReleaseStatusDetail,
  Report,
  ReportReason,
  ReportSubject,
  User,
} from "./types";

export interface HubRequest {
  method: "GET" | "POST" | "PUT" | "DELETE";
  /** API path below the version prefix, e.g. `/mods/my-pack/ratings`. */
  path: string;
  query?: Record<string, string | number | undefined>;
  /** JSON-serialized, except FormData, which goes through as multipart.
   *  Custom transports that cannot carry FormData should reject it rather
   *  than stringify it. */
  body?: unknown;
  /**
   * Bytes-sent progress, 0→1, for uploads big enough to be worth watching.
   * Optional on both sides: a transport that cannot measure it simply never
   * calls it, and the caller falls back to an indeterminate indicator.
   */
  onProgress?: (fraction: number) => void;
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

/** Where one owner's gallery lives: `/mods/{slug}` or `/tools/{slug}`. */
function galleryPath(owner: MediaOwner): string {
  return `/${owner.type}s/${encodeURIComponent(owner.slug)}`;
}

function buildPath(req: HubRequest): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(req.query ?? {})) {
    if (v !== undefined && v !== "") q.set(k, String(v));
  }
  const qs = q.toString();
  return `${PREFIX}${req.path}${qs ? `?${qs}` : ""}`;
}

/**
 * The one thing `fetch` still cannot do: report how much of the body has gone
 * out. Used only when a caller asks for progress on a multipart body, so every
 * other request stays on `fetch`.
 */
function xhrSend(
  url: string,
  req: HubRequest,
  headers: Record<string, string>,
  withCredentials: boolean,
): Promise<HubResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(req.method, url, true);
    xhr.withCredentials = withCredentials;
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    xhr.upload.addEventListener("progress", (e) => {
      // Chunked bodies report no total; leave those to the caller's fallback.
      if (e.lengthComputable && e.total > 0) req.onProgress?.(e.loaded / e.total);
    });
    xhr.addEventListener("load", () => {
      // The bytes are gone even if the server is still thinking about them.
      req.onProgress?.(1);
      let body: unknown = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        body = null;
      }
      resolve({ status: xhr.status, body });
    });
    xhr.addEventListener("error", () =>
      reject(new HubError(0, "network_error", "The upload could not reach the hub.")),
    );
    xhr.addEventListener("abort", () =>
      reject(new HubError(0, "aborted", "The upload was cancelled.")),
    );
    xhr.send(req.body as XMLHttpRequestBodyInit);
  });
}

function fetchTransport(options: HubClientOptions): HubTransport {
  const doFetch = options.fetchImpl ?? globalThis.fetch;
  return async (req) => {
    // FormData sets its own multipart boundary header; JSON declares itself.
    const isForm = typeof FormData !== "undefined" && req.body instanceof FormData;
    const headers: Record<string, string> = {};
    if (req.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
    if (options.token) headers["Authorization"] = `Bearer ${options.token}`;

    const url = `${options.baseUrl ?? ""}${buildPath(req)}`;
    if (req.onProgress && isForm && typeof XMLHttpRequest !== "undefined") {
      return xhrSend(url, req, headers, !options.token);
    }

    const res = await doFetch(url, {
      method: req.method,
      headers,
      body: req.body === undefined ? undefined : isForm ? (req.body as FormData) : JSON.stringify(req.body),
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

  async listMedia(owner: MediaOwner): Promise<Media[]> {
    const r = await this.call<{ media: Media[] }>({
      method: "GET",
      path: `${galleryPath(owner)}/media`,
    });
    return r.media;
  }

  /**
   * Submit a screenshot or video to a gallery. On a mod it lands as
   * `pending` (check `status` on the result) unless the caller is a
   * moderator; on a tool only moderators may submit at all.
   * Multipart under the hood — a custom transport must support FormData.
   * `onProgress` reports bytes sent, 0→1, where the transport can measure it.
   */
  uploadMedia(
    owner: MediaOwner,
    file: Blob,
    altText: string,
    onProgress?: (fraction: number) => void,
  ): Promise<Media> {
    const form = new FormData();
    form.set("file", file);
    form.set("alt_text", altText);
    return this.call({
      method: "POST",
      path: `${galleryPath(owner)}/media`,
      body: form,
      onProgress,
    });
  }

  deleteMedia(id: string): Promise<{ ok: boolean }> {
    return this.call({ method: "DELETE", path: `/media/${encodeURIComponent(id)}` });
  }

  /** View beacons; the server folds repeats per viewer per hour. */
  recordMediaView(id: string): Promise<{ views: number }> {
    return this.call({ method: "POST", path: `/media/${encodeURIComponent(id)}/view` });
  }

  recordModView(slug: string): Promise<{ views: number }> {
    return this.call({ method: "POST", path: `/mods/${encodeURIComponent(slug)}/view` });
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

  /** The gallery review queue. Moderators only. */
  async listModerationMedia(status: MediaStatus = "pending"): Promise<QueuedMedia[]> {
    const r = await this.call<{ media: QueuedMedia[] }>({
      method: "GET",
      path: "/moderation/media",
      query: { status },
    });
    return r.media;
  }

  decideMedia(id: string, action: "approve" | "reject"): Promise<{ ok: boolean }> {
    return this.call({
      method: "POST",
      path: `/moderation/media/${encodeURIComponent(id)}`,
      body: { action },
    });
  }

  /** The report queue. Moderators only. */
  async listReports(status: Report["status"] = "open"): Promise<Report[]> {
    const r = await this.call<{ reports: Report[] }>({
      method: "GET",
      path: "/moderation/reports",
      query: { status },
    });
    return r.reports;
  }

  decideReport(id: string, action: "resolve" | "dismiss"): Promise<{ ok: boolean }> {
    return this.call({
      method: "POST",
      path: `/moderation/reports/${encodeURIComponent(id)}`,
      body: { action },
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
