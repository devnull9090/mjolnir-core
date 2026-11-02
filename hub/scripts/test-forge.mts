import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { zipSync } from "fflate";
import { app } from "../src/lib/api/app";
import { ForgePackSchema } from "../src/lib/api/forge";
import { forgePackageId, requiredForgePackages } from "../src/lib/api/forge-content";
import { ManifestSchema } from "../src/lib/api/manifest";
import { scanArchive } from "../src/lib/api/scan";
import { getModPage, listPublishedMods } from "../src/lib/api/queries";
import { hub } from "./hub-harness.mjs";

const json = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));
const block = {
  id: "platform_4x4", name: "Platform 4 × 4", category: "platform",
  tag: "objects\\mjolnir\\forge\\test-pack\\platform_4x4",
  dimensions_m: [4, 4, 0.5], snap_m: 0.5,
};
const pack = { schema_version: 1, id: "test-pack", blocks: [block] };
const manifest = {
  schema_version: 1, name: "Test pack", version: "1.0.0", type: "content", summary: "Modular models",
  forge_pack: pack, deps: [{ slug: "mjolnir-ce-runtime", range: "=1.15.0" }],
};

function archive(value: unknown = manifest, packages: string[] = [], options: { kind?: number; prefix?: string; emptyCas?: boolean } = {}) {
  const toc = new Uint8Array(144 + Math.max(1, packages.length) * 12);
  toc.set(new TextEncoder().encode("-==--==--==--==-"));
  new DataView(toc.buffer).setUint32(20, 144, true);
  new DataView(toc.buffer).setUint32(24, Math.max(1, packages.length), true);
  for (const [i, name] of packages.entries()) {
    new DataView(toc.buffer).setBigUint64(144 + i * 12, forgePackageId(name), true);
    toc[144 + i * 12 + 11] = options.kind ?? 1;
  }
  const prefix = options.prefix ?? "content";
  return zipSync({
    "mjolnir.json": json(value),
    [`${prefix}/test-pack_P.utoc`]: toc,
    [`${prefix}/test-pack_P.ucas`]: new Uint8Array(options.emptyCas ? [] : [1]),
  });
}

test("Forge profile package IDs match the shared Rust UE CityHash vectors", () => {
  const vectors = JSON.parse(readFileSync(new URL("../../tools/fixtures/forge-package-ids.json", import.meta.url), "utf8")) as { name: string; id_hex: string }[];
  assert.equal(vectors.length, 15);
  for (const v of vectors) assert.equal(forgePackageId(v.name).toString(16).padStart(16, "0"), v.id_hex, v.name);
  assert.throws(() => forgePackageId("/Game/A"));
  assert.throws(() => forgePackageId("/Game/MJOLNIR/Forge/éé/Materials/M_ForgeGlassCyan"));
});

test("surface profiles require their own cooked masters and textures, not stray or bulk chunks", () => {
  for (const profile of ["glass_cyan", "teleporter_green"] as const) {
    const catalog = ForgePackSchema.parse({ ...pack, blocks: [{ ...block, surfaces: [{ slot: 7, profile }] }] });
    const value = { ...manifest, forge_pack: catalog };
    const required = requiredForgePackages(catalog);
    assert.equal(required.length, profile === "glass_cyan" ? 1 : 4);
    const good = scanArchive(archive(value, required));
    assert.equal(good.verdict, "pass", JSON.stringify(good.findings));
    for (const absent of required) {
      const result = scanArchive(archive(value, required.filter((p) => p !== absent)));
      assert.equal(result.verdict, "fail");
      assert.ok(result.findings.some((f) => f.code === "missing_forge_package" && f.message.includes(absent)));
    }
    for (const invalid of [
      archive(value, required.map((p) => p.replace("/test-pack/", "/other-pack/"))),
      archive(value, required, { kind: 2 }),
      archive(value, required, { prefix: "docs" }),
      archive(value, required, { emptyCas: true }),
    ]) assert.ok(scanArchive(invalid).findings.some((f) => f.code === "missing_forge_package"));
  }
  assert.equal(scanArchive(archive()).verdict, "pass", "legacy pack needs no surface cook");
});

test("a Forge pack is scanned as inert content and keeps its inventory", () => {
  const result = scanArchive(archive());
  assert.equal(result.verdict, "pass", JSON.stringify(result.findings));
  assert.deepEqual(result.manifest?.forge_pack, pack);
  assert.deepEqual(result.manifest?.deps, manifest.deps);
});

test("Forge release versions fit the launcher and native exact identity without changing ordinary releases", () => {
  for (const version of ["0.0.0", "1.2.3-alpha.0", "18446744073709551615.0.0", `1.0.0-${"a".repeat(90)}`]) {
    assert.equal(ManifestSchema.safeParse({ ...manifest, version }).success, true, version);
  }
  for (const version of ["01.0.0", "1.0.0-01", "1.0.0-a..b", "1.0.0-.", "1.0.0+build",
    "18446744073709551616.0.0", `1.0.0-${"a".repeat(91)}`]) {
    assert.equal(ManifestSchema.safeParse({ ...manifest, version }).success, false, version);
    assert.ok(scanArchive(archive({ ...manifest, version })).findings.some((f) => f.code === "bad_manifest"));
  }
  assert.equal(ManifestSchema.safeParse({ ...manifest, forge_pack: undefined, version: "01.0.0" }).success, true);
});

test("stable IDs prevent cross-pack tag aliases, path traversal and duplicate blocks", () => {
  for (const changed of [
    { ...block, id: "../platform" },
    { ...block, tag: "objects\\mjolnir\\forge\\other-pack\\platform_4x4" },
    { ...block, tag: "objects\\mjolnir\\forge\\test-pack\\different" },
    { ...block, tag: "objects/mjolnir/forge/test-pack/platform_4x4" },
    { ...block, tag: "objects\\mjolnir\\forge\\test-pack\\..\\platform_4x4" },
  ]) {
    assert.equal(ForgePackSchema.safeParse({ ...pack, blocks: [changed] }).success, false);
  }
  assert.equal(ForgePackSchema.safeParse({ ...pack, blocks: [block, block] }).success, false);
  assert.equal(ForgePackSchema.safeParse({ ...pack, id: "../pack" }).success, false);
});

test("inventory bounds, schema, names, categories and finite positive dimensions are enforced", () => {
  for (const changed of [
    { ...block, dimensions_m: [4, 4] }, { ...block, dimensions_m: [4, 0, 1] },
    { ...block, dimensions_m: [4, -1, 1] }, { ...block, dimensions_m: [Infinity, 4, 1] },
    { ...block, dimensions_m: [NaN, 4, 1] }, { ...block, snap_m: 0 },
    { ...block, snap_m: Infinity }, { ...block, category: "../platform" }, { ...block, name: " " },
  ]) assert.equal(ForgePackSchema.safeParse({ ...pack, blocks: [changed] }).success, false);
  assert.equal(ForgePackSchema.safeParse({ ...pack, schema_version: 2 }).success, false);
  assert.equal(ForgePackSchema.safeParse({ ...pack, blocks: [] }).success, false);
  assert.equal(ForgePackSchema.safeParse({ ...pack, blocks: Array(257).fill(block) }).success, false);
});

test("map archives reference packs through dependencies instead of claiming a pack inventory", () => {
  const map = { code: "TST", title: "Test map", modes: ["slayer"] };
  assert.equal(ManifestSchema.safeParse({ ...manifest, type: "map", map }).success, false);
  const valid = ManifestSchema.parse({
    schema_version: 1, name: "Test map", version: "1.0.0", type: "map", map,
    deps: [{ slug: "test-pack", range: "=1.0.0" }],
  });
  assert.equal(valid.deps[0].range, "=1.0.0");
});

test("light metadata is bounded data, survives scanning and accepts older packs", () => {
  const light = { offset_m: [0, -0.35, 3.1], color_rgb: [1, 0.05, 0.03], intensity_cd: 70, radius_m: 8 };
  const lit = { ...manifest, forge_pack: { ...pack, blocks: [{ ...block, light }] } };
  assert.deepEqual(scanArchive(archive(lit)).manifest?.forge_pack?.blocks[0].light, light);
  assert.equal(ForgePackSchema.safeParse({ ...pack, blocks: [{ ...block, light: null }] }).success, true);
  for (const invalid of [
    { ...light, offset_m: [0, 101, 0] }, { ...light, offset_m: [0, 0] },
    { ...light, color_rgb: [1, -0.1, 0] }, { ...light, color_rgb: [1, 1.1, 0] },
    { ...light, intensity_cd: 0 }, { ...light, intensity_cd: 10001 },
    { ...light, radius_m: 0 }, { ...light, radius_m: 101 },
    { ...light, radius_m: Infinity }, { ...light, offset_m: [NaN, 0, 0] },
    { ...light, script: "anything" }, {},
  ]) assert.equal(ForgePackSchema.safeParse({ ...pack, blocks: [{ ...block, light: invalid }] }).success, false);
});

test("lift, door and surface metadata survive scanning with strict conservative bounds", () => {
  const lift = { offset_m: [0, 0, .45], size_m: [4, 4, 3.5], direction: [0, 0, 1], acceleration_m_s2: 20, max_speed_m_s: 4.5, negates_gravity: true };
  const door = { travel_m: 4, speed_m_s: 4, trigger_size_m: [8, 16, 6], hold_open_s: 2 };
  const surfaces = [{ slot: 7, profile: "teleporter_green" }];
  const utility = { ...block, lift, door, surfaces };
  const catalog = ForgePackSchema.parse({ ...pack, blocks: [utility] });
  const result = scanArchive(archive({ ...manifest, forge_pack: catalog }, requiredForgePackages(catalog)));
  assert.equal(result.verdict, "pass", JSON.stringify(result.findings));
  assert.deepEqual(result.manifest?.forge_pack?.blocks[0], utility);
  const rejects = (change: unknown) => assert.equal(ForgePackSchema.safeParse({ ...pack, blocks: [{ ...utility, ...(change as object) }] }).success, false);
  for (const invalid of [{ ...lift, direction: [0, 0, 0] }, { ...lift, direction: [0, 0, 1.01] },
    { ...lift, size_m: [4, 4, 101] }, { ...lift, acceleration_m_s2: 100.1 }, { ...lift, max_speed_m_s: 30.1 },
    { ...lift, offset_m: [Infinity, 0, 0] }, { ...lift, negates_gravity: 1 }, { ...lift, script: "x" }]) rejects({ lift: invalid });
  for (const invalid of [{ ...door, travel_m: 0 }, { ...door, travel_m: 16.01 }, { ...door, speed_m_s: 8.01 },
    { ...door, trigger_size_m: [8, 16, 33] }, { ...door, hold_open_s: -1 }, { ...door, hold_open_s: 11 },
    { ...door, hold_open_s: NaN }, { ...door, command: "x" }]) rejects({ door: invalid });
  rejects({ dimensions_m: [65, 1, 1] });
  for (const invalid of [[{ slot: 16, profile: "glass_cyan" }], [{ slot: 1.5, profile: "glass_cyan" }],
    [{ slot: 0, profile: "arbitrary" }], [{ slot: 0, profile: "glass_cyan", path: "x" }],
    [{ slot: 0, profile: "glass_cyan" }, { slot: 0, profile: "teleporter_green" }]]) rejects({ surfaces: invalid });
  assert.equal(ForgePackSchema.safeParse({ ...pack, blocks: [{ ...block, lift: null, door: null, surfaces: null }] }).success, true);
});

test("pack metadata does not permit source scripts or an archive with no installed container", () => {
  const bad = scanArchive(zipSync({ "mjolnir.json": json(manifest), "forge/generator.py": json("script") }));
  assert.equal(bad.verdict, "fail");
  assert.ok(bad.findings.some((f) => f.code === "forbidden_file"));
  const absent = scanArchive(zipSync({ "mjolnir.json": json(manifest) }));
  assert.equal(absent.verdict, "fail");
  assert.ok(absent.findings.some((f) => f.code === "no_content"));
});

test("publishing retains versioned inventory, dependencies, download, catalog and visibility rules", async () => {
  const h = hub();
  const key = await h.account("author");
  h.sqlite.prepare("UPDATE api_keys SET scopes = 'mods:write' WHERE user_id = 'author'").run();
  const stored = new Map<string, Uint8Array>();
  Object.assign(h.env, { MODS_BUCKET: {
    async put(path: string, bytes: Uint8Array) { stored.set(path, bytes); },
    async get(path: string) {
      const bytes = stored.get(path);
      return bytes ? { body: new ReadableStream({ start(c) { c.enqueue(bytes); c.close(); } }) } : null;
    },
  } });

  async function publish(slug: string, value: typeof manifest = manifest) {
    const created = await h.call("POST", "/mods", key, { slug, name: slug });
    assert.equal(created.status, 201, JSON.stringify(created.body));
    const release = await h.call("POST", `/mods/${slug}/releases`, key, { version: value.version });
    assert.equal(release.status, 201, JSON.stringify(release.body));
    const id = release.body.id as string;
    const uploaded = await app.request(`/api/v1/releases/${id}/archive`, {
      method: "PUT", headers: { authorization: `Bearer ${key}`, "content-type": "application/zip" },
      body: archive(value),
    }, h.env, { waitUntil() {}, passThroughOnException() {}, props: {} } as never);
    assert.equal(uploaded.status, 200, await uploaded.text());
    const result = await h.call("POST", `/releases/${id}/complete`, key);
    return { id, modId: created.body.id, result };
  }

  const { id, modId, result } = await publish("test-pack");
  assert.equal(result.status, 200, JSON.stringify(result.body));
  assert.equal(result.body.status, "published", JSON.stringify(result.body));
  const inventory = await h.call("GET", `/releases/${id}/forge-pack`, null);
  assert.equal(inventory.status, 200);
  assert.deepEqual(inventory.body.forge_pack, pack);
  assert.deepEqual(inventory.body.deps, manifest.deps);
  assert.equal(inventory.body.slug, "test-pack");
  assert.match(inventory.body.sha256 as string, /^[a-f0-9]{64}$/);
  const catalog = await h.call("GET", "/mods?forge=1", null);
  assert.equal(catalog.status, 200);
  assert.deepEqual((catalog.body.mods as { slug: string }[]).map((m) => m.slug), ["test-pack"]);
  assert.deepEqual((await h.call("GET", "/mods?forge=0", null)).body.mods, []);
  const listing = await listPublishedMods(h.env.DB as never, { forge: true });
  assert.equal(listing[0].category, "forge");
  const page = await getModPage(h.env.DB as never, "test-pack");
  assert.deepEqual(page?.forgePack, { version: "1.0.0", pack });
  const downloaded = await app.request(`/api/v1/releases/${id}/download`, undefined, h.env,
    { waitUntil() {}, passThroughOnException() {}, props: {} } as never);
  assert.equal(downloaded.status, 200);
  assert.deepEqual(new Uint8Array(await downloaded.arrayBuffer()), archive());

  const impostor = await publish("another-pack");
  assert.equal(impostor.result.body.status, "rejected");
  assert.ok((impostor.result.body.findings as { code: string }[]).some((f) => f.code === "forge_pack_id_mismatch"));
  assert.equal((await h.call("GET", `/releases/${impostor.id}/forge-pack`, null)).status, 404);

  h.sqlite.prepare("UPDATE mod_releases SET status = 'yanked' WHERE id = ?1").run(id);
  assert.equal((await h.call("GET", `/releases/${id}/forge-pack`, null)).status, 404);
  assert.deepEqual((await h.call("GET", "/mods?forge=1", null)).body.mods, []);
  h.sqlite.prepare("UPDATE mod_releases SET status = 'published' WHERE id = ?1").run(id);
  h.sqlite.prepare("UPDATE mods SET status = 'hidden' WHERE id = ?1").run(modId);
  assert.equal((await h.call("GET", `/releases/${id}/forge-pack`, null)).status, 404);
});
