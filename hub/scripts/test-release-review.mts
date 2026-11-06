/**
 * The release review queue: a real upload through PUT /archive and /complete
 * into release_reviews, read back from GET /moderation/releases and decided
 * with POST /moderation/releases/{id}, against every migration in an in-memory
 * SQLite (hub-harness.mts). Archives are the shape test-scan.mts builds.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { unzipSync, zipSync } from "fflate";

import { app } from "../src/lib/api/app";
import { hub } from "./hub-harness.mjs";

const { sqlite, env, account, call } = hub();

const stored = new Map<string, Uint8Array>();
/** What the next multipart upload completes to. */
let multipartBytes: Uint8Array = new Uint8Array();
Object.assign(env, {
  MODS_BUCKET: {
    async put(path: string, bytes: Uint8Array) {
      stored.set(path, bytes);
    },
    async get(path: string) {
      const bytes = stored.get(path);
      return bytes
        ? {
            body: new ReadableStream({
              start(c) {
                c.enqueue(bytes);
                c.close();
              },
            }),
          }
        : null;
    },
    resumeMultipartUpload(path: string) {
      return {
        async complete() {
          stored.set(path, multipartBytes);
          return { size: multipartBytes.length };
        },
      };
    },
  },
});

const author = await account("author");
const rival = await account("rival");
const player = await account("player");
const moderator = await account("mod", "moderator");
// Everyone but `player` can publish, so a refusal below is about whose mod it
// is, not what their key may do.
const stranger = await account("stranger");
const coauthor = await account("coauthor");
const contributor = await account("contributor");
sqlite
  .prepare(
    `UPDATE api_keys SET scopes = 'mods:write'
     WHERE user_id IN ('author', 'rival', 'mod', 'stranger', 'coauthor', 'contributor')`,
  )
  .run();

const json = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));

/** ue_iostore::bank::sample, as test-scan.mts builds it. */
function bank(id: number): Uint8Array {
  const words = (...values: number[]) => new Uint8Array(new Uint32Array(values).buffer);
  const section = (tag: string, ...body: Uint8Array[]) => {
    const size = body.reduce((n, part) => n + part.length, 0);
    return [new TextEncoder().encode(tag), words(size), ...body];
  };
  const parts = [
    ...section("BKHD", words(150, id), new Uint8Array(32)),
    ...section("DIDX", words(7, 0, 5)),
    ...section("DATA", new TextEncoder().encode("media")),
    ...section("HIRC", words(1), new Uint8Array([2]), words(8, 11), new TextEncoder().encode("body")),
  ];
  const out = new Uint8Array(parts.reduce((n, part) => n + part.length, 0));
  let at = 0;
  for (const part of parts) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}

function toc(): Uint8Array {
  const out = new Uint8Array(156);
  out.set(new TextEncoder().encode("-==--==--==--==-"));
  new DataView(out.buffer).setUint32(20, 144, true);
  new DataView(out.buffer).setUint32(24, 1, true);
  return out;
}

/** A pack: a map when `code` is given, plain content otherwise. */
function archive(
  version: string,
  opts: { code?: string; banks?: number[]; title?: string; modes?: string[] } = {},
): Uint8Array {
  const { code, banks = [], title = `Map ${code}`, modes = ["slayer"] } = opts;
  const container = code ? `pakchunk987-MJOLNIR-${code}_P` : "pakchunk988-MJOLNIR-CONTENT_P";
  const members: Record<string, Uint8Array> = {
    "mjolnir.json": json({
      schema_version: 1,
      name: "Test",
      version,
      type: code ? "map" : "content",
      summary: "Test",
      ...(code ? { map: { code, title, modes } } : {}),
    }),
    [`content/${container}.utoc`]: toc(),
    [`content/${container}.ucas`]: new Uint8Array([1]),
  };
  if (code) {
    members["map/level.json"] = json({});
    members["map/registration.json"] = json({ code, from: "B40" });
  }
  for (const id of banks) members[`content/${container}/${id}.bnk`] = bank(id);
  return zipSync(members);
}

async function upload(id: string, bytes: Uint8Array, key = author) {
  return app.request(
    `/api/v1/releases/${id}/archive`,
    {
      method: "PUT",
      headers: { authorization: `Bearer ${key}`, "content-type": "application/zip" },
      body: bytes as BodyInit,
    },
    env,
    { waitUntil() {}, passThroughOnException() {}, props: {} } as never,
  );
}

/** What a player's launcher gets: the archive's bytes, or null if it may not have them. */
async function download(id: string): Promise<Uint8Array | null> {
  const res = await app.request(`/api/v1/releases/${id}/download`, {}, env, {
    waitUntil() {},
    passThroughOnException() {},
    props: {},
  } as never);
  return res.status === 200 ? new Uint8Array(await res.arrayBuffer()) : null;
}

/** A new mod's first release, uploaded and scanned. */
async function publish(slug: string, version: string, bytes: Uint8Array, key = author) {
  const created = await call("POST", "/mods", key, { slug, name: `Mod ${slug}` });
  assert.equal(created.status, 201, JSON.stringify(created.body));
  return addRelease(slug, version, bytes, key);
}

/** Another release of a mod, uploaded and scanned. */
async function addRelease(slug: string, version: string, bytes: Uint8Array, key = author) {
  sqlite.exec(`DELETE FROM rate_counters`); // the publish budget, not what's under test
  const release = await call("POST", `/mods/${slug}/releases`, key, { version });
  assert.equal(release.status, 201, JSON.stringify(release.body));
  const id = release.body.id as string;
  const put = await upload(id, bytes, key);
  assert.equal(put.status, 200, await put.text());
  const done = await call("POST", `/releases/${id}/complete`, key);
  assert.equal(done.status, 200, JSON.stringify(done.body));
  return { id, status: done.body.status as string, findings: done.body.findings as { code: string }[] };
}

interface Queued {
  release_id: string;
  mod_slug: string;
  mod_name: string;
  mod_status: string;
  version: string;
  map_code: string | null;
  map_title: string | null;
  file_size: number | null;
  sha256: string | null;
  banks: string[] | null;
  findings: { level: string; code: string; message: string }[];
  uploader: string;
  reason: string | null;
}

async function queue(state = "pending"): Promise<Queued[]> {
  const r = await call("GET", `/moderation/releases?state=${state}`, moderator);
  assert.equal(r.status, 200, JSON.stringify(r.body));
  return r.body.releases as Queued[];
}

const queued = async (id: string) => (await queue()).find((r) => r.release_id === id);
const statusOf = (table: string, id: string) =>
  sqlite.prepare(`SELECT status FROM ${table} WHERE id = ?1`).all(id)[0].status;
const decide = (id: string, action: "approve" | "reject", reason?: string) =>
  call("POST", `/moderation/releases/${id}`, moderator, { action, reason });

/** A map as the public route shows it, or null if it isn't listed. */
async function listed(code: string) {
  const r = await call("GET", `/maps/${code}`, null);
  return r.status === 200 ? r.body : null;
}

/** The listing's row, public or not. A draft mod's would still reach lobbies and matches by code. */
const listingRow = (code: string) =>
  sqlite.prepare(`SELECT mod_id FROM map_listings WHERE code = ?1`).all(code)[0];

/** A published map, for an update to land on. */
async function live(slug: string, code: string) {
  const { id } = await publish(slug, "1.0.0", archive("1.0.0", { code }));
  assert.equal((await decide(id, "approve")).status, 200);
  return (await listed(code))!;
}

test("a map with banks waits, and the queue says what it carries", async () => {
  const { id, status } = await publish("banked", "1.0.0", archive("1.0.0", { code: "BNK", banks: [99, 100] }));
  assert.equal(status, "pending");
  const row = await queued(id);
  assert.ok(row);
  assert.equal(row.mod_slug, "banked");
  assert.equal(row.mod_name, "Mod banked");
  assert.equal(row.mod_status, "draft");
  assert.equal(row.version, "1.0.0");
  assert.equal(row.map_code, "BNK");
  assert.equal(row.map_title, "Map BNK");
  assert.equal(row.uploader, "author display");
  assert.ok(row.file_size && row.file_size > 0);
  assert.deepEqual([...(row.banks ?? [])].sort(), [
    "content/pakchunk987-MJOLNIR-BNK_P/100.bnk",
    "content/pakchunk987-MJOLNIR-BNK_P/99.bnk",
  ]);
  assert.ok(row.findings.some((f) => f.code === "awaiting_review"), JSON.stringify(row.findings));
});

test("a release with banks and no map has no map fields", async () => {
  const { id, status } = await publish("no-map", "1.0.0", archive("1.0.0", { banks: [101] }));
  assert.equal(status, "pending");
  const row = await queued(id);
  assert.ok(row);
  assert.equal(row.map_code, null);
  assert.equal(row.map_title, null);
  assert.equal(row.banks?.length, 1);
});

test("a map with no banks says none, which is not the same as unknown", async () => {
  const { id } = await publish("plain-map", "1.0.0", archive("1.0.0", { code: "PLN" }));
  assert.deepEqual((await queued(id))?.banks, []);

  // A row scanned before migration 0025 has no record at all.
  sqlite.prepare(`UPDATE mod_releases SET banks_json = NULL WHERE id = ?1`).run(id);
  assert.equal((await queued(id))?.banks, null);
});

test("the findings are the latest scan's, and a release shows once", async () => {
  const { id } = await publish("rescanned", "1.0.0", archive("1.0.0", { code: "RSC" }));
  // Same second as the real scan, so only the insert order tells them apart.
  const at = sqlite.prepare(`SELECT created_at FROM release_scans WHERE release_id = ?1`).all(id)[0].created_at;
  sqlite
    .prepare(
      `INSERT INTO release_scans (id, release_id, verdict, findings, scanner_version, created_at)
       VALUES ('newer', ?1, 'pass', ?2, 'test', ?3)`,
    )
    .run(id, JSON.stringify([{ level: "warning", code: "newest", message: "Newest." }]), at);
  const rows = (await queue()).filter((r) => r.release_id === id);
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0].findings.map((f) => f.code), ["newest"]);
});

test("the queue is for moderators", async () => {
  for (const [method, path, body] of [
    ["GET", "/moderation/releases", undefined],
    ["POST", "/moderation/releases/whatever", { action: "approve" }],
  ] as const) {
    assert.equal((await call(method, path, null, body)).status, 401);
    assert.equal((await call(method, path, player, body)).status, 403);
    assert.equal((await call(method, path, author, body)).status, 403);
  }
});

test("a non-moderator's decision changes nothing", async () => {
  const { id } = await publish("not-yours", "1.0.0", archive("1.0.0", { code: "NOT" }));
  assert.equal((await call("POST", `/moderation/releases/${id}`, author, { action: "approve" })).status, 403);
  assert.equal(statusOf("mod_releases", id), "pending");
  assert.ok(await queued(id));
});

test("approval publishes the release and its draft mod", async () => {
  const bytes = archive("1.0.0", { code: "APR", banks: [102] });
  const { id } = await publish("to-approve", "1.0.0", bytes);
  assert.equal(await download(id), null);
  const r = await call("POST", `/moderation/releases/${id}`, moderator, { action: "approve", reason: "Listened to it." });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.equal(statusOf("mod_releases", id), "published");
  assert.equal(sqlite.prepare(`SELECT status FROM mods WHERE slug = 'to-approve'`).all()[0].status, "published");
  assert.equal(await queued(id), undefined);
  const decided = (await queue("approved")).find((x) => x.release_id === id);
  assert.equal(decided?.reason, "Listened to it.");
  assert.equal(decided?.banks?.length, 1);
  const log = sqlite.prepare(`SELECT actor_id, detail FROM audit_log WHERE action = 'release_approve' AND subject_id = ?1`).all(id);
  assert.deepEqual(log.map((l) => ({ ...l })), [{ actor_id: "mod", detail: "Listened to it." }]);
  assert.deepEqual(await download(id), bytes);
  // A note on an approval is the moderators' own.
  assert.equal((await call("GET", `/releases/${id}`, author)).body.review_reason, null);
});

test("rejection keeps the mod a draft and records the reason", async () => {
  const { id } = await publish("to-reject", "1.0.0", archive("1.0.0", { code: "REJ" }));
  const r = await call("POST", `/moderation/releases/${id}`, moderator, { action: "reject", reason: "Stolen map." });
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.equal(statusOf("mod_releases", id), "rejected");
  assert.equal(sqlite.prepare(`SELECT status FROM mods WHERE slug = 'to-reject'`).all()[0].status, "draft");
  assert.equal(await queued(id), undefined);
  assert.equal((await queue("rejected")).find((x) => x.release_id === id)?.reason, "Stolen map.");
  assert.equal(await download(id), null);
  // The author reads it where they read the scan.
  assert.equal((await call("GET", `/releases/${id}`, author)).body.review_reason, "Stolen map.");
});

test("a decided release can't be decided again", async () => {
  const { id } = await publish("decided", "1.0.0", archive("1.0.0", { code: "DCD" }));
  assert.equal((await call("POST", `/moderation/releases/${id}`, moderator, { action: "reject", reason: "No." })).status, 200);
  const again = await call("POST", `/moderation/releases/${id}`, moderator, { action: "approve" });
  assert.equal(again.status, 404);
  // The page shows this as it comes, so it has to read as a sentence.
  assert.match(again.body.message as string, /no longer waiting/);
  assert.equal(statusOf("mod_releases", id), "rejected");
});

test("moderators and trusted authors skip the queue, banks and all", async () => {
  const own = await publish("mods-own", "1.0.0", archive("1.0.0", { code: "MOD", banks: [103] }), moderator);
  assert.equal(own.status, "published");
  assert.equal(await queued(own.id), undefined);

  sqlite.prepare(`UPDATE users SET trust_level = 2 WHERE id = 'author'`).run();
  const trusted = await publish("trusted", "1.0.0", archive("1.0.0", { code: "TRS", banks: [104] }));
  sqlite.prepare(`UPDATE users SET trust_level = 0 WHERE id = 'author'`).run();
  assert.equal(trusted.status, "published");
  assert.equal(await queued(trusted.id), undefined);
  // Their banks are on record even so.
  const banks = sqlite.prepare(`SELECT banks_json FROM mod_releases WHERE id = ?1`).all(trusted.id)[0].banks_json;
  assert.equal(JSON.parse(banks as string).length, 1);
});

/** An archive the scan refuses. */
function refused(version: string, code: string): Uint8Array {
  const members = unzipSync(archive(version, { code }));
  members["content/extra.exe"] = new Uint8Array([1]);
  return zipSync(members);
}

test("a new archive starts a held release's review over", async () => {
  const { id } = await publish("swapped", "1.0.0", archive("1.0.0", { code: "SWP" }));
  assert.ok(await queued(id));

  const bad = refused("1.0.0", "SWP");
  assert.equal((await upload(id, bad)).status, 200);

  assert.equal(await queued(id), undefined);
  const approve = await call("POST", `/moderation/releases/${id}`, moderator, { action: "approve" });
  assert.equal(approve.status, 404, JSON.stringify(approve.body));
  assert.equal(statusOf("mod_releases", id), "pending");
  assert.equal(await download(id), null);

  // The scan decides what happens next.
  const done = await call("POST", `/releases/${id}/complete`, author);
  assert.equal(done.body.status, "rejected", JSON.stringify(done.body));
  assert.equal(await queued(id), undefined);
});

test("so does one uploaded in parts, the way a big map goes up", async () => {
  const { id } = await publish("swapped-parts", "1.0.0", archive("1.0.0", { code: "SWM" }));
  assert.ok(await queued(id));

  multipartBytes = refused("1.0.0", "SWM");
  const done = await call("POST", `/releases/${id}/archive/multipart/upload-1/complete`, author, {
    parts: [{ part: 1, etag: "etag" }],
  });
  assert.equal(done.status, 200, JSON.stringify(done.body));

  assert.equal(await queued(id), undefined);
  assert.equal((await call("POST", `/moderation/releases/${id}`, moderator, { action: "approve" })).status, 404);
  assert.equal(await download(id), null);
});

test("a published release's archive stays put", async () => {
  const { id } = await publish("settled", "1.0.0", archive("1.0.0", { code: "SET" }));
  await call("POST", `/moderation/releases/${id}`, moderator, { action: "approve" });
  assert.equal((await upload(id, refused("1.0.0", "SET"))).status, 409);
  assert.equal(statusOf("mod_releases", id), "published");
});

test("a held release uploaded again comes back with its new scan", async () => {
  const { id } = await publish("reuploaded", "1.0.0", archive("1.0.0", { code: "RUP" }));
  assert.deepEqual((await queued(id))?.banks, []);

  const fixed = archive("1.0.0", { code: "RUP", banks: [105] });
  assert.equal((await upload(id, fixed)).status, 200);
  assert.equal((await call("POST", `/releases/${id}/complete`, author)).body.status, "pending");

  const row = await queued(id);
  assert.equal(row?.banks?.length, 1);
  assert.equal((await call("POST", `/moderation/releases/${id}`, moderator, { action: "approve" })).status, 200);
  assert.deepEqual(await download(id), fixed);
});

test("a rejected release uploaded again goes back through the queue", async () => {
  const { id } = await publish("second-try", "1.0.0", archive("1.0.0", { code: "TRY" }));
  await call("POST", `/moderation/releases/${id}`, moderator, { action: "reject", reason: "Fix the spawns." });

  assert.equal((await upload(id, archive("1.0.0", { code: "TRY", banks: [106] }))).status, 200);
  assert.equal((await call("POST", `/releases/${id}/complete`, author)).body.status, "pending");

  const row = await queued(id);
  assert.equal(row?.reason, null);
  assert.equal(row?.banks?.length, 1);
  assert.equal((await call("GET", `/releases/${id}`, author)).body.review_reason, null);
});

test("a rescan that no longer holds the release leaves nothing to decide", async () => {
  const { id } = await publish("promoted", "1.0.0", archive("1.0.0", { code: "PRM" }));
  sqlite.prepare(`UPDATE users SET trust_level = 2 WHERE id = 'author'`).run();
  const done = await call("POST", `/releases/${id}/complete`, author);
  sqlite.prepare(`UPDATE users SET trust_level = 0 WHERE id = 'author'`).run();
  assert.equal(done.body.status, "published");
  assert.equal(await queued(id), undefined);
  assert.equal(sqlite.prepare(`SELECT COUNT(*) AS n FROM release_reviews WHERE release_id = ?1`).all(id)[0].n, 0);
});

test("a review left behind by an older hub isn't offered", async () => {
  const { id } = await publish("stale-row", "1.0.0", archive("1.0.0", { code: "STL" }));
  sqlite.prepare(`UPDATE mod_releases SET status = 'rejected' WHERE id = ?1`).run(id);
  assert.equal(await queued(id), undefined);
});

test("a decision is about the archive the moderator read", async () => {
  const { id } = await publish("read-this", "1.0.0", archive("1.0.0", { code: "RDT" }));
  const read = (await queued(id))?.sha256;
  assert.match(read ?? "", /^[a-f0-9]{64}$/);

  // Replaced and rescanned behind an open page: it's back in the queue, with
  // different contents, under the same id.
  assert.equal((await upload(id, archive("1.0.0", { code: "RDT", banks: [107] }))).status, 200);
  assert.equal((await call("POST", `/releases/${id}/complete`, author)).body.status, "pending");

  const stale = await call("POST", `/moderation/releases/${id}`, moderator, { action: "approve", sha256: read });
  assert.equal(stale.status, 409, JSON.stringify(stale.body));
  assert.equal(statusOf("mod_releases", id), "pending");

  const current = (await queued(id))?.sha256;
  assert.notEqual(current, read);
  assert.equal(
    (await call("POST", `/moderation/releases/${id}`, moderator, { action: "approve", sha256: current })).status,
    200,
  );
});

test("a held update leaves the public listing as it is", async () => {
  const before = await live("held-update", "HUP");
  assert.equal(before.title, "Map HUP");

  const held = archive("1.1.0", { code: "HUP", title: "Renamed", modes: ["slayer", "ctf"] });
  const { status } = await addRelease("held-update", "1.1.0", held);
  assert.equal(status, "pending");
  assert.deepEqual(await listed("HUP"), before);
});

test("a held update's new code stays off the listing too", async () => {
  const before = await live("held-code", "HC1");
  const { status } = await addRelease("held-code", "1.1.0", archive("1.1.0", { code: "HC2" }));
  assert.equal(status, "pending");
  assert.deepEqual(await listed("HC1"), before);
  assert.equal(await listed("HC2"), null);
});

test("the queue shows the held code and title, not the listing's", async () => {
  await live("shown", "SHW");
  const { id } = await addRelease("shown", "1.1.0", archive("1.1.0", { code: "SH2", title: "New name" }));
  const row = await queued(id);
  assert.equal(row?.map_code, "SH2");
  assert.equal(row?.map_title, "New name");
});

test("approval applies the held map block", async () => {
  await live("applied", "APL");
  sqlite.prepare(`UPDATE map_listings SET size = 'large' WHERE code = 'APL'`).run();
  const { id } = await addRelease(
    "applied",
    "1.1.0",
    archive("1.1.0", { code: "AP2", title: "Approved name", modes: ["slayer", "ctf"] }),
  );
  assert.equal((await decide(id, "approve")).status, 200);

  assert.equal(await listed("APL"), null);
  const now = await listed("AP2");
  assert.equal(now?.title, "Approved name");
  assert.deepEqual(now?.modes, ["slayer", "ctf"]);
  assert.equal((now?.release as { id: string }).id, id);
  // A field the release left out keeps what the listing said.
  assert.equal(now?.size, "large");
  // What was approved stays readable once the listing could move on.
  const decided = (await queue("approved")).find((x) => x.release_id === id);
  assert.equal(decided?.map_code, "AP2");
  assert.equal(decided?.map_title, "Approved name");
});

test("rejection leaves the listing as it was", async () => {
  const before = await live("refused-update", "RFU");
  const { id } = await addRelease(
    "refused-update",
    "1.1.0",
    archive("1.1.0", { code: "RF2", title: "Refused name", modes: ["ctf"] }),
  );
  assert.equal((await decide(id, "reject", "No.")).status, 200);
  assert.deepEqual(await listed("RFU"), before);
  assert.equal(listingRow("RF2"), undefined);
  // The record of what was refused is the release's, not the listing's.
  const decided = (await queue("rejected")).find((x) => x.release_id === id);
  assert.equal(decided?.map_title, "Refused name");
});

test("a held first release has no listing until it's approved", async () => {
  const { id } = await publish("no-listing", "1.0.0", archive("1.0.0", { code: "NLS", title: "Waiting" }));
  assert.equal(listingRow("NLS"), undefined);
  assert.equal((await queued(id))?.map_title, "Waiting");

  assert.equal((await decide(id, "approve")).status, 200);
  assert.equal((await listed("NLS"))?.title, "Waiting");
});

test("a release that skips the queue lists at once", async () => {
  const own = await publish("listed-now", "1.0.0", archive("1.0.0", { code: "LSN" }), moderator);
  assert.equal(own.status, "published");
  assert.equal((await listed("LSN"))?.title, "Map LSN");

  const update = await addRelease("listed-now", "1.1.0", archive("1.1.0", { code: "LSN", title: "Moved on" }), moderator);
  assert.equal(update.status, "published");
  assert.equal((await listed("LSN"))?.title, "Moved on");
});

test("a rescan that stops holding the release lists it", async () => {
  const { id } = await publish("listed-late", "1.0.0", archive("1.0.0", { code: "LSL" }));
  assert.equal(listingRow("LSL"), undefined);
  sqlite.prepare(`UPDATE users SET trust_level = 2 WHERE id = 'author'`).run();
  const done = await call("POST", `/releases/${id}/complete`, author);
  sqlite.prepare(`UPDATE users SET trust_level = 0 WHERE id = 'author'`).run();
  assert.equal(done.body.status, "published");
  assert.equal((await listed("LSL"))?.title, "Map LSL");
});

test("a held release with no map block leaves the listing alone", async () => {
  const before = await live("banks-only", "BKO");
  const { id } = await addRelease("banks-only", "1.1.0", archive("1.1.0", { banks: [110] }));
  // The mod is still that map, which is what the moderator wants to know.
  assert.equal((await queued(id))?.map_code, "BKO");
  assert.equal((await decide(id, "approve")).status, 200);
  const { release: newest, ...rest } = (await listed("BKO"))!;
  const { release: oldest, ...earlier } = before;
  assert.deepEqual(rest, earlier);
  assert.notDeepEqual(newest, oldest);
});

test("a release held before the hub kept its map block still reads and decides", async () => {
  const before = await live("older-hold", "OLD");
  const { id } = await addRelease("older-hold", "1.1.0", archive("1.1.0", { code: "OLD", title: "Not kept" }));
  sqlite.prepare(`UPDATE mod_releases SET map_json = NULL WHERE id = ?1`).run(id);

  assert.equal((await queued(id))?.map_code, "OLD");
  assert.equal((await queued(id))?.map_title, "Map OLD");
  assert.equal((await decide(id, "approve")).status, 200);
  assert.equal((await listed("OLD"))?.title, before.title);
});

test("approving an older release doesn't take the listing back", async () => {
  await live("out-of-order", "OOO");
  const older = await addRelease("out-of-order", "1.1.0", archive("1.1.0", { code: "OOO", title: "Older" }));
  const newer = await addRelease("out-of-order", "1.2.0", archive("1.2.0", { code: "OOO", title: "Newer" }));
  // Both after 1.0.0, a minute apart, since a test runs inside one second.
  sqlite.prepare(`UPDATE mod_releases SET created_at = datetime('now', '+1 minute') WHERE id = ?1`).run(older.id);
  sqlite.prepare(`UPDATE mod_releases SET created_at = datetime('now', '+2 minutes') WHERE id = ?1`).run(newer.id);

  assert.equal((await decide(newer.id, "approve")).status, 200);
  assert.equal((await decide(older.id, "approve")).status, 200);
  assert.equal(statusOf("mod_releases", older.id), "published");
  const now = await listed("OOO");
  assert.equal(now?.title, "Newer");
  assert.equal((now?.release as { id: string }).id, newer.id);
});

test("a held first release holds its code against other authors", async () => {
  const { id } = await publish("first-claim", "1.0.0", archive("1.0.0", { code: "CLM" }));
  assert.equal((await queued(id))?.map_code, "CLM");

  const second = await publish("second-claim", "1.0.0", archive("1.0.0", { code: "CLM" }), rival);
  assert.equal(second.status, "rejected");
  assert.ok(second.findings.some((f) => f.code === "map_code_taken"), JSON.stringify(second.findings));
  assert.equal(await queued(second.id), undefined);
  assert.equal(listingRow("CLM"), undefined);

  // Not even an author who'd skip the queue.
  const trusted = await publish("third-claim", "1.0.0", archive("1.0.0", { code: "CLM" }), moderator);
  assert.equal(trusted.status, "rejected");
  assert.equal(listingRow("CLM"), undefined);
});

test("a held update holds the code it's moving to", async () => {
  await live("moving", "MV1");
  await addRelease("moving", "1.1.0", archive("1.1.0", { code: "MV2" }));
  const other = await publish("wants-mv2", "1.0.0", archive("1.0.0", { code: "MV2" }), rival);
  assert.equal(other.status, "rejected");
  assert.ok(other.findings.some((f) => f.code === "map_code_taken"), JSON.stringify(other.findings));
});

test("an author's own releases share a held code", async () => {
  const first = await publish("own-code", "1.0.0", archive("1.0.0", { code: "OWN" }));
  const second = await addRelease("own-code", "1.1.0", archive("1.1.0", { code: "OWN" }));
  assert.equal(second.status, "pending");
  assert.ok(await queued(first.id));
  assert.ok(await queued(second.id));

  // Rejecting one leaves the other holding it.
  assert.equal((await decide(first.id, "reject", "Older.")).status, 200);
  const other = await publish("wants-own", "1.0.0", archive("1.0.0", { code: "OWN" }), rival);
  assert.equal(other.status, "rejected");
});

test("rejection frees a held code", async () => {
  const { id } = await publish("gives-up", "1.0.0", archive("1.0.0", { code: "FRE" }));
  assert.equal((await decide(id, "reject", "No.")).status, 200);

  const next = await publish("takes-over", "1.0.0", archive("1.0.0", { code: "FRE" }), rival);
  assert.equal(next.status, "pending", JSON.stringify(next.findings));
  assert.equal((await queued(next.id))?.map_code, "FRE");
});

test("a release out of the queue holds nothing a moderator can't see", async () => {
  const { id } = await publish("left-queue", "1.0.0", archive("1.0.0", { code: "LFT" }));
  // A new archive with no /complete: nothing in the queue answers for the code.
  assert.equal((await upload(id, archive("1.0.0", { code: "LFT", banks: [111] }))).status, 200);
  assert.equal(await queued(id), undefined);

  const next = await publish("took-it", "1.0.0", archive("1.0.0", { code: "LFT" }), rival);
  assert.equal(next.status, "pending", JSON.stringify(next.findings));

  // And the code is gone when the first one comes back.
  const back = await call("POST", `/releases/${id}/complete`, author);
  assert.equal(back.body.status, "rejected", JSON.stringify(back.body));
});

test("a code two scans claimed at once goes to the first approval", async () => {
  const first = await publish("same-instant-a", "1.0.0", archive("1.0.0", { code: "SIA" }));
  const second = await publish("same-instant-b", "1.0.0", archive("1.0.0", { code: "SIB" }), rival);
  // What two /complete calls in the same instant leave: each read before the
  // other wrote, so neither saw a claim.
  sqlite
    .prepare(`UPDATE mod_releases SET map_json = json_set(map_json, '$.code', 'SIA') WHERE id = ?1`)
    .run(second.id);

  assert.equal((await decide(first.id, "approve")).status, 200);
  const refused = await decide(second.id, "approve");
  assert.equal(refused.status, 409, JSON.stringify(refused.body));
  assert.equal(refused.body.error, "map_code_taken");
  // The page shows this as it comes, so it has to read as a sentence.
  assert.match(refused.body.message as string, /SIA/);

  // Nothing of the refused approval stuck, and a moderator can still reject it.
  assert.equal(statusOf("mod_releases", second.id), "pending");
  assert.equal(sqlite.prepare(`SELECT status FROM mods WHERE slug = 'same-instant-b'`).all()[0].status, "draft");
  assert.equal(listingRow("SIA")?.mod_id, sqlite.prepare(`SELECT id FROM mods WHERE slug = 'same-instant-a'`).all()[0].id);
  assert.equal(
    sqlite.prepare(`SELECT COUNT(*) AS n FROM audit_log WHERE action = 'release_approve' AND subject_id = ?1`).all(second.id)[0].n,
    0,
  );
  assert.equal((await decide(second.id, "reject", "Code taken.")).status, 200);
});

interface Listed {
  id: string;
  version: string;
  status: string;
  findings: { code: string }[];
  review_reason: string | null;
}

/** What the manage page reads. */
async function listAll(slug: string, key: string | null) {
  const r = await call("GET", `/mods/${slug}/releases/all`, key);
  return { status: r.status, body: r.body, releases: (r.body.releases ?? []) as Listed[] };
}

/** A live mod with something in every state an author needs to hear about. */
async function liveMod(slug: string, code: string) {
  const published = await publish(slug, "1.0.0", archive("1.0.0", { code }));
  assert.equal((await decide(published.id, "approve")).status, 200);
  const rejected = await addRelease(slug, "1.1.0", archive("1.1.0", { code }));
  assert.equal((await decide(rejected.id, "reject", "Spawns are in the wall.")).status, 200);
  const held = await addRelease(slug, "1.2.0", archive("1.2.0", { code }));
  assert.equal(held.status, "pending");
  return { published, rejected, held };
}

/** A draft mod whose only release a moderator turned down. */
async function rejectedDraft(slug: string, code: string) {
  const { id } = await publish(slug, "1.0.0", archive("1.0.0", { code }));
  assert.equal((await decide(id, "reject", "Stolen map.")).status, 200);
  return id;
}

test("a mod's owner sees every release, with what the scan and the moderator said", async () => {
  const { published, rejected, held } = await liveMod("every-status", "EVS");
  const { status, releases } = await listAll("every-status", author);
  assert.equal(status, 200);
  // Newest first, even inside one second of created_at.
  assert.deepEqual(releases.map((r) => r.id), [held.id, rejected.id, published.id]);
  const byId = new Map(releases.map((r) => [r.id, r]));

  assert.equal(byId.get(published.id)?.status, "published");
  assert.equal(byId.get(published.id)?.review_reason, null);
  assert.equal(byId.get(rejected.id)?.status, "rejected");
  assert.equal(byId.get(rejected.id)?.review_reason, "Spawns are in the wall.");
  assert.equal(byId.get(held.id)?.status, "pending");
  assert.ok(byId.get(held.id)?.findings.some((f) => f.code === "awaiting_review"));

  // The list and the single release can't tell different stories.
  for (const release of releases) {
    assert.deepEqual(release, (await call("GET", `/releases/${release.id}`, author)).body);
  }
});

test("a release with no archive yet is listed too", async () => {
  await rejectedDraft("no-archive", "NOA");
  const created = await call("POST", "/mods/no-archive/releases", author, { version: "1.0.1" });
  assert.equal(created.status, 201, JSON.stringify(created.body));
  const row = (await listAll("no-archive", author)).releases.find((r) => r.version === "1.0.1");
  assert.equal(row?.status, "pending");
  assert.deepEqual(row?.findings, []);
});

test("a stranger can't list another author's unpublished releases", async () => {
  await liveMod("not-for-strangers", "NFS");
  const draft = await rejectedDraft("draft-not-for-strangers", "DNS");

  for (const slug of ["not-for-strangers", "draft-not-for-strangers"]) {
    const anonymous = await listAll(slug, null);
    assert.equal(anonymous.status, 401);
    assert.equal(anonymous.body.releases, undefined);
    // A key that could publish, on an account that has nothing to do with it.
    const refused = await listAll(slug, stranger);
    assert.equal(refused.status, 403);
    assert.equal(refused.body.releases, undefined);
    assert.equal((await listAll(slug, player)).status, 403);
  }
  // Nor does the draft's own page open for them.
  assert.equal((await call("GET", "/mods/draft-not-for-strangers", stranger)).status, 404);
  assert.equal((await listAll("draft-not-for-strangers", author)).releases[0].id, draft);
});

test("the public list stays published-only, whoever asks", async () => {
  const { published } = await liveMod("public-view", "PBV");
  for (const key of [null, stranger, author, moderator]) {
    const r = await call("GET", "/mods/public-view/releases", key);
    assert.equal(r.status, 200);
    const rows = r.body.releases as Record<string, unknown>[];
    assert.deepEqual(rows.map((x) => x.id), [published.id]);
    assert.equal(rows[0].findings, undefined);
  }
  // A draft has no public list at all, its own author included.
  await rejectedDraft("public-draft", "PBD");
  assert.equal((await call("GET", "/mods/public-draft/releases", null)).status, 404);
  assert.equal((await call("GET", "/mods/public-draft/releases", author)).status, 404);
});

test("authors and moderators see a draft and its releases, contributors don't", async () => {
  const id = await rejectedDraft("shared-draft", "SHD");
  const modId = sqlite.prepare(`SELECT id FROM mods WHERE slug = 'shared-draft'`).all()[0].id;
  const addAuthor = sqlite.prepare(`INSERT INTO mod_authors (mod_id, user_id, role) VALUES (?1, ?2, ?3)`);
  addAuthor.run(modId, "coauthor", "author");
  addAuthor.run(modId, "contributor", "contributor");

  for (const key of [coauthor, moderator]) {
    const { status, releases } = await listAll("shared-draft", key);
    assert.equal(status, 200);
    assert.deepEqual(releases.map((r) => [r.id, r.review_reason]), [[id, "Stolen map."]]);
    assert.equal((await call("GET", "/mods/shared-draft", key)).status, 200);
  }
  assert.equal((await listAll("shared-draft", contributor)).status, 403);
  assert.equal((await call("GET", "/mods/shared-draft", contributor)).status, 404);
});

test("the list wants a key that can publish, and doesn't spend its budget", async () => {
  await rejectedDraft("key-scope", "KSC");
  sqlite.exec(`DELETE FROM rate_counters`);
  assert.equal((await listAll("key-scope", author)).status, 200);
  assert.equal(sqlite.prepare(`SELECT COUNT(*) AS n FROM rate_counters`).all()[0].n, 0);

  // The owner's own launcher key, which can't publish.
  sqlite.prepare(`UPDATE api_keys SET scopes = 'lobbies:write' WHERE user_id = 'author'`).run();
  const narrow = await listAll("key-scope", author);
  sqlite.prepare(`UPDATE api_keys SET scopes = 'mods:write' WHERE user_id = 'author'`).run();
  assert.equal(narrow.status, 403);
  assert.equal(narrow.body.error, "insufficient_scope");
});

test("no such mod is a 404, not a refusal", async () => {
  assert.equal((await listAll("never-made", author)).status, 404);
});
