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
const player = await account("player");
const moderator = await account("mod", "moderator");
sqlite.prepare(`UPDATE api_keys SET scopes = 'mods:write' WHERE user_id IN ('author', 'mod')`).run();

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
function archive(version: string, opts: { code?: string; banks?: number[] } = {}): Uint8Array {
  const { code, banks = [] } = opts;
  const container = code ? `pakchunk987-MJOLNIR-${code}_P` : "pakchunk988-MJOLNIR-CONTENT_P";
  const members: Record<string, Uint8Array> = {
    "mjolnir.json": json({
      schema_version: 1,
      name: "Test",
      version,
      type: code ? "map" : "content",
      summary: "Test",
      ...(code ? { map: { code, title: `Map ${code}`, modes: ["slayer"] } } : {}),
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
  sqlite.exec(`DELETE FROM rate_counters`); // the publish budget, not what's under test
  const created = await call("POST", "/mods", key, { slug, name: `Mod ${slug}` });
  assert.equal(created.status, 201, JSON.stringify(created.body));
  const release = await call("POST", `/mods/${slug}/releases`, key, { version });
  assert.equal(release.status, 201, JSON.stringify(release.body));
  const id = release.body.id as string;
  const put = await upload(id, bytes, key);
  assert.equal(put.status, 200, await put.text());
  const done = await call("POST", `/releases/${id}/complete`, key);
  assert.equal(done.status, 200, JSON.stringify(done.body));
  return { id, status: done.body.status as string };
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
});

test("a decided release can't be decided again", async () => {
  const { id } = await publish("decided", "1.0.0", archive("1.0.0", { code: "DCD" }));
  assert.equal((await call("POST", `/moderation/releases/${id}`, moderator, { action: "reject", reason: "No." })).status, 200);
  assert.equal((await call("POST", `/moderation/releases/${id}`, moderator, { action: "approve" })).status, 404);
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
