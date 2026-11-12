/**
 * Releases that need a newer launcher (`requires`, src/lib/api/clients.ts):
 * what the scan and publish measure, and what each kind of client sees on the
 * routes launchers read. Real uploads through PUT /archive and /complete
 * against every migration in an in-memory SQLite (hub-harness.mts).
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { zipSync } from "fflate";

import { app } from "../src/lib/api/app";
import { clientOf, compatible, UPDATE_LAUNCHER } from "../src/lib/api/clients";
import { listMaps } from "../src/lib/api/maps";
import { scanArchive } from "../src/lib/api/scan";
import { hub } from "./hub-harness.mjs";

const { sqlite, env, account, call } = hub();
const ctx = { waitUntil() {}, passThroughOnException() {}, props: {} } as never;

const stored = new Map<string, Uint8Array>();
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
  },
});

const author = await account("author");
const other = await account("other");
const newcomer = await account("newcomer");
const moderator = await account("mod", "moderator");
sqlite.prepare(`UPDATE api_keys SET scopes = 'mods:write'`).run();
// Maps from these two publish without review; `newcomer`'s wait for a moderator.
sqlite.prepare(`UPDATE users SET trust_level = 2 WHERE id IN ('author', 'other')`).run();

const json = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));

/** A 12-byte chunk ID: u64 id, u16 index, pad, type (8 = shader library, 1 = package data). */
function chunk(id: number, type: number): Uint8Array {
  const out = new Uint8Array(12);
  new DataView(out.buffer).setBigUint64(0, BigInt(id), true);
  out[11] = type;
  return out;
}

function toc(ids: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(144 + 12 * ids.length);
  out.set(new TextEncoder().encode("-==--==--==--==-"));
  new DataView(out.buffer).setUint32(20, 144, true);
  new DataView(out.buffer).setUint32(24, ids.length, true);
  ids.forEach((id, i) => out.set(id, 144 + 12 * i));
  return out;
}

/** A pack with one container `content/<container>` holding `ids`; a map when `code` is given. */
function archive(version: string, container: string, ids: Uint8Array[], code?: string): Uint8Array {
  const members: Record<string, Uint8Array> = {
    "mjolnir.json": json({
      schema_version: 1,
      name: "Test",
      version,
      type: code ? "map" : "content",
      summary: "Test",
      ...(code ? { map: { code, title: `Map ${code}`, modes: ["slayer"] } } : {}),
    }),
    [`content/${container}.utoc`]: toc(ids),
    [`content/${container}.ucas`]: new Uint8Array([1]),
  };
  if (code) {
    members["map/level.json"] = json({});
    members["map/registration.json"] = json({ code, from: "B40" });
  }
  return zipSync(members);
}

/** A shader library at chunk number `n` with library chunk `lib`, plus a package. */
const pack = (version: string, n: number | null, lib: number, code?: string) =>
  archive(
    version,
    `${n === null ? "" : `pakchunk${n}-`}MJOLNIR-${code ?? "CONTENT"}_P`,
    [chunk(lib, 8), chunk(lib + 1, 1)],
    code,
  );

async function upload(id: string, bytes: Uint8Array, key: string) {
  return app.request(
    `/api/v1/releases/${id}/archive`,
    {
      method: "PUT",
      headers: { authorization: `Bearer ${key}`, "content-type": "application/zip" },
      body: bytes as BodyInit,
    },
    env,
    ctx,
  );
}

let clock = 0;
/** A release uploaded and scanned; each one later than the last. */
async function release(slug: string, version: string, bytes: Uint8Array, key = author) {
  if (!sqlite.prepare(`SELECT 1 FROM mods WHERE slug = ?1`).all(slug).length) {
    const created = await call("POST", "/mods", key, { slug, name: `Mod ${slug}` });
    assert.equal(created.status, 201, JSON.stringify(created.body));
  }
  sqlite.exec(`DELETE FROM rate_counters`);
  const made = await call("POST", `/mods/${slug}/releases`, key, { version });
  assert.equal(made.status, 201, JSON.stringify(made.body));
  const id = made.body.id as string;
  // created_at has one-second resolution; "newest" must not hang on a tie.
  clock += 1;
  sqlite
    .prepare(`UPDATE mod_releases SET created_at = datetime('2026-01-01', ?2) WHERE id = ?1`)
    .run(id, `+${clock} minutes`);
  const put = await upload(id, bytes, key);
  assert.equal(put.status, 200, await put.text());
  const done = await call("POST", `/releases/${id}/complete`, key);
  assert.equal(done.status, 200, JSON.stringify(done.body));
  return {
    id,
    status: done.body.status as string,
    requires: done.body.requires as string[],
    findings: done.body.findings as { code: string; message: string }[],
  };
}

const stored_requires = (id: string) =>
  sqlite.prepare(`SELECT requires FROM mod_releases WHERE id = ?1`).all(id)[0].requires;

// ── Clients ──────────────────────────────────────────────────────────

const CLIENTS = {
  legacy: {} as Record<string, string>,
  current: {
    "User-Agent": "MJOLNIR-Launcher/0.24.0",
    "X-MJOLNIR-Launcher": "0.24.0",
    "X-MJOLNIR-Features": "local-chunk-numbers",
  },
  currentWithout: { "X-MJOLNIR-Launcher": "0.24.0", "User-Agent": "MJOLNIR-Launcher/0.24.0" },
  browser: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" },
};
type Kind = keyof typeof CLIENTS;

async function get(path: string, kind: Kind, extra: Record<string, string> = {}) {
  const res = await app.request(`/api/v1${path}`, { headers: { ...CLIENTS[kind], ...extra } }, env, ctx);
  const type = res.headers.get("content-type") ?? "";
  const body = type.includes("json") ? ((await res.json()) as Record<string, unknown>) : null;
  return { status: res.status, body, vary: res.headers.get("vary") ?? "" };
}

test("client kinds come from the headers", () => {
  const h = (o: Record<string, string>) => new Headers(o);
  assert.equal(clientOf(h(CLIENTS.legacy)).kind, "legacy");
  assert.equal(clientOf(h({ "User-Agent": " " })).kind, "legacy");
  assert.equal(clientOf(h(CLIENTS.browser)).kind, "other");
  const current = clientOf(h({ "X-MJOLNIR-Launcher": "0.24.0", "X-MJOLNIR-Features": " a, local-chunk-numbers ,," }));
  assert.equal(current.kind, "launcher");
  assert.deepEqual([...current.features].sort(), ["a", "local-chunk-numbers"]);
  assert.equal(clientOf(h(CLIENTS.currentWithout)).features.size, 0);
  assert.ok(compatible(clientOf(h(CLIENTS.browser)), ["anything"]));
  assert.ok(!compatible(clientOf(h(CLIENTS.legacy)), ["local-chunk-numbers"]));
  assert.ok(compatible(clientOf(h(CLIENTS.legacy)), []));
});

// ── The scan ─────────────────────────────────────────────────────────

test("the scan gates a shader library outside 900-999 or with no number", () => {
  const cases: [number | null, boolean][] = [
    [978, false],
    [900, false],
    [999, false],
    [899, true],
    [1000, true],
    [20001, true],
    [null, true],
  ];
  for (const [n, gated] of cases) {
    const scan = scanArchive(pack("1.0.0", n, 0x1000));
    assert.equal(scan.verdict, "pass", JSON.stringify(scan.findings));
    assert.deepEqual(scan.requires, gated ? ["local-chunk-numbers"] : [], `pakchunk${n}`);
    assert.equal(scan.findings.some((f) => f.code === "needs_new_launcher" && f.level === "warning"), gated);
  }
});

test("the scan does not gate a container with no shader library, whatever its number", () => {
  for (const name of ["pakchunk20001-MJOLNIR-X_P", "MJOLNIR-X_P", "pakchunk978-MJOLNIR-X_P"]) {
    const scan = scanArchive(archive("1.0.0", name, [chunk(0x2000, 1), chunk(0x2001, 2)]));
    assert.equal(scan.verdict, "pass", JSON.stringify(scan.findings));
    assert.deepEqual(scan.requires, [], name);
  }
});

// ── Publish: stored, and the collision rule ──────────────────────────

const L = 0x10_0000; // one library chunk several mods share

test("requires is stored, NULL for none, and on every release shape", async () => {
  const plain = await release("plain", "1.0.0", pack("1.0.0", 978, 0x3000));
  assert.equal(plain.status, "published");
  assert.deepEqual(plain.requires, []);
  assert.equal(stored_requires(plain.id), null);

  const high = await release("high", "1.0.0", pack("1.0.0", 20001, 0x3100));
  assert.equal(high.status, "published");
  assert.deepEqual(high.requires, ["local-chunk-numbers"]);
  assert.equal(stored_requires(high.id), '["local-chunk-numbers"]');

  const browser = await get(`/mods/high/releases`, "browser");
  assert.deepEqual((browser.body!.releases as { requires: string[] }[])[0].requires, ["local-chunk-numbers"]);
  const status = await get(`/releases/${plain.id}`, "browser");
  assert.deepEqual(status.body!.requires, []);
});

test("a library shared with another mod's ungated release gates the newcomer only", async () => {
  const original = await release("original", "1.0.0", pack("1.0.0", 978, L));
  assert.deepEqual(original.requires, []);

  const copy = await release("copy", "1.0.0", pack("1.0.0", 978, L), other);
  assert.deepEqual(copy.requires, ["local-chunk-numbers"]);
  const finding = copy.findings.find((f) => f.code === "needs_new_launcher");
  assert.ok(finding?.message.includes("original"), JSON.stringify(copy.findings));

  // The owner's next release shares it with its own mod and a gated copy: neither counts.
  const update = await release("original", "1.1.0", pack("1.1.0", 978, L));
  assert.deepEqual(update.requires, []);
  assert.equal(stored_requires(original.id), null);
});

test("a release gated already never gates the next one to share its library", async () => {
  const gated = await release("gated-first", "1.0.0", pack("1.0.0", 20001, 0x20_0000));
  assert.deepEqual(gated.requires, ["local-chunk-numbers"]);
  const second = await release("in-range-second", "1.0.0", pack("1.0.0", 950, 0x20_0000), other);
  assert.deepEqual(second.requires, []);
  assert.ok(!second.findings.some((f) => f.code === "needs_new_launcher"));
});

test("a held release that another mod beat to its library is gated at approval", async () => {
  const held = await release("held-map", "1.0.0", pack("1.0.0", 960, 0x30_0000, "HLD"), newcomer);
  assert.equal(held.status, "pending");
  assert.deepEqual(held.requires, []);
  await release("beat-it", "1.0.0", pack("1.0.0", 961, 0x30_0000), other);
  const decided = await call("POST", `/moderation/releases/${held.id}`, moderator, { action: "approve" });
  assert.equal(decided.status, 200, JSON.stringify(decided.body));
  assert.equal(stored_requires(held.id), '["local-chunk-numbers"]');
});

// ── What each client sees ────────────────────────────────────────────

const ids = { old: "", gated: "", only: "" };

test("setup: a map with an ungated release and a newer gated one", async () => {
  const old = await release("gated-map", "1.0.0", pack("1.0.0", 978, 0x40_0000, "GTM"));
  const gated = await release("gated-map", "1.1.0", pack("1.1.0", 20001, 0x41_0000, "GTM"));
  const only = await release("only-gated", "1.0.0", pack("1.0.0", null, 0x42_0000, "ONG"));
  assert.deepEqual([old.status, gated.status, only.status], ["published", "published", "published"]);
  assert.deepEqual(gated.requires, ["local-chunk-numbers"]);
  Object.assign(ids, { old: old.id, gated: gated.id, only: only.id });
});

test("GET /mods/{slug}/releases leaves out what the client cannot install", async () => {
  const versions = async (kind: Kind, slug = "gated-map") => {
    const r = await get(`/mods/${slug}/releases`, kind);
    assert.equal(r.status, 200);
    assert.match(r.vary, /User-Agent, X-MJOLNIR-Launcher, X-MJOLNIR-Features/);
    return (r.body!.releases as { version: string }[]).map((x) => x.version);
  };
  assert.deepEqual(await versions("legacy"), ["1.0.0"]);
  assert.deepEqual(await versions("current"), ["1.1.0", "1.0.0"]);
  assert.deepEqual(await versions("currentWithout"), ["1.0.0"]);
  assert.deepEqual(await versions("browser"), ["1.1.0", "1.0.0"]);
});

test("with only releases it cannot install, a launcher gets the newest of them", async () => {
  const r = await get(`/mods/only-gated/releases`, "legacy");
  assert.deepEqual((r.body!.releases as { id: string }[]).map((x) => x.id), [ids.only]);
  const without = await get(`/mods/only-gated/releases`, "currentWithout");
  assert.equal((without.body!.releases as unknown[]).length, 1);
  // The legacy launcher then asks for it and is told to update.
  const status = await get(`/releases/${ids.only}`, "legacy");
  assert.equal(status.body!.status, UPDATE_LAUNCHER);
});

test("GET /releases/{id} tells a legacy launcher to update, and no one else", async () => {
  const status = async (id: string, kind: Kind) => {
    const r = await get(`/releases/${id}`, kind);
    assert.equal(r.status, 200);
    assert.match(r.vary, /X-MJOLNIR-Features/);
    return r.body!.status;
  };
  assert.equal(await status(ids.gated, "legacy"), UPDATE_LAUNCHER);
  assert.equal(await status(ids.gated, "current"), "published");
  assert.equal(await status(ids.gated, "currentWithout"), "published");
  assert.equal(await status(ids.gated, "browser"), "published");
  assert.equal(await status(ids.old, "legacy"), "published");
  // What the old launcher prints.
  assert.equal(
    `Release is ${UPDATE_LAUNCHER}, not published`,
    "Release is for a newer MJOLNIR launcher: update the launcher from mjolnircore.com/download, not published",
  );
});

test("GET /releases/{id}/download refuses a legacy launcher with 409, before counting it", async () => {
  const count = () =>
    sqlite.prepare(`SELECT download_count FROM mod_releases WHERE id = ?1`).all(ids.gated)[0].download_count;
  const before = count();
  const refused = await get(`/releases/${ids.gated}/download`, "legacy");
  assert.equal(refused.status, 409);
  assert.equal(refused.body!.error, "needs_new_launcher");
  assert.match(String(refused.body!.message), /update the launcher from mjolnircore\.com\/download/);
  assert.match(refused.vary, /X-MJOLNIR-Launcher/);
  assert.equal(count(), before);
  for (const kind of ["current", "currentWithout", "browser"] as const) {
    assert.equal((await get(`/releases/${ids.gated}/download`, kind)).status, 200, kind);
  }
  assert.equal((await get(`/releases/${ids.old}/download`, "legacy")).status, 200);
});

test("/maps and /maps/{code} embed the newest release the client can install", async () => {
  const embedded = async (kind: Kind, code = "GTM") => {
    const one = await get(`/maps/${code}`, kind);
    assert.equal(one.status, 200);
    assert.match(one.vary, /User-Agent, X-MJOLNIR-Launcher, X-MJOLNIR-Features/);
    const list = await get(`/maps?official=0`, kind);
    assert.match(list.vary, /X-MJOLNIR-Features/);
    const listed = (list.body!.maps as { code: string; release: { id: string } }[]).find((m) => m.code === code);
    const release = one.body!.release as { id: string; requires: string[] };
    assert.equal(listed?.release.id, release.id, `${kind} list vs one`);
    return release.id;
  };
  assert.equal(await embedded("legacy"), ids.old);
  assert.equal(await embedded("current"), ids.gated);
  assert.equal(await embedded("currentWithout"), ids.old);
  assert.equal(await embedded("browser"), ids.gated);
  // None it can install: the newest of all, so the install reaches the update message.
  assert.equal(await embedded("legacy", "ONG"), ids.only);
  // The website's server components call listMaps directly and see the newest.
  const site = (await listMaps(env.DB as never)).find((m) => m.code === "GTM");
  assert.equal(site?.release?.id, ids.gated);
  assert.deepEqual(site?.release?.requires, ["local-chunk-numbers"]);
});

test("Vary keeps CORS's Origin", async () => {
  const r = await get(`/maps/GTM`, "browser", { Origin: "https://example.test" });
  assert.match(r.vary, /Origin/);
  assert.match(r.vary, /X-MJOLNIR-Launcher/);
});
