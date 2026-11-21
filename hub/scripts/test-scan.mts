import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";
import { zipSync } from "fflate";

import { checkBank, MAX_BANK_BYTES } from "../src/lib/api/banks";
import { needsReview } from "../src/lib/api/publish";
import { scanArchive, scanArchiveStream } from "../src/lib/api/scan";

const json = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));
const state = {
  height: "flux_state/height.exr", velocity: "flux_state/velocity.exr",
  centre: [3600, 2300, 1182], res: [192, 160], cell: 20, height_cm: 2000, capture: -318,
};
// Opaque EXR content remains streamed/hash-only, like other image assets.
const texture = new Uint8Array(513).map((_, i) => i & 255);

function fixture(water = true): Record<string, Uint8Array> {
  const toc = new Uint8Array(156);
  toc.set(new TextEncoder().encode("-==--==--==--==-"));
  new DataView(toc.buffer).setUint32(20, 144, true);
  new DataView(toc.buffer).setUint32(24, 1, true);
  const members: Record<string, Uint8Array> = {
    "mjolnir.json": json({
      schema_version: 1, name: "Test map", version: "0.3.0", type: "map", summary: "Test map",
      map: { code: "TST", title: "Test map", modes: ["slayer", "team_slayer", "ctf"] },
    }),
    "map/level.json": json(water ? { flux: { state } } : {}),
    "map/registration.json": json({ code: "TST", from: "B40" }),
    "content/pakchunk987-MJOLNIR-TST_P.utoc": toc,
    "content/pakchunk987-MJOLNIR-TST_P.ucas": new Uint8Array([1]),
  };
  if (water) {
    members["map/flux_state/state.json"] = json(state);
    members["map/flux_state/height.exr"] = texture;
    members["map/flux_state/velocity.exr"] = texture;
  }
  return members;
}

function rejects(members: Record<string, Uint8Array>, code: string) {
  const scan = scanArchive(zipSync(members));
  assert.equal(scan.verdict, "fail", JSON.stringify(scan.findings));
  assert.ok(scan.findings.some((f) => f.code === code), JSON.stringify(scan.findings));
}

/** ue_iostore::bank::sample: one media file and one HIRC record. */
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

const CONTAINER = "pakchunk987-MJOLNIR-TST_P";
const WARTHOG = 833622567;

function withBanks(banks: Record<string, Uint8Array>) {
  return { ...fixture(false), ...banks };
}

test("the bank fixture is the launcher's", () => {
  // crates/ue-iostore/src/bank.rs asserts the same hash of its sample.
  assert.equal(createHash("sha1").update(bank(99)).digest("hex"), "b76d27ed276b91306dc5ebb6fd2b80e847f57d79");
});

test("a pack with real banks passes and says so", () => {
  const name = `content/${CONTAINER}/99.bnk`;
  const scan = scanArchive(zipSync(withBanks({ [name]: bank(99), [`content/${CONTAINER}/100.bnk`]: bank(100) })));
  assert.equal(scan.verdict, "pass", JSON.stringify(scan.findings));
  assert.equal(scan.banks.length, 2);
  assert.ok(scan.hashes[name]);
});

test("a pack with no banks reports none", () => {
  assert.deepEqual(scanArchive(zipSync(fixture(false))).banks, []);
});

test("a .pak stays forbidden, whatever it holds", () => {
  rejects(withBanks({ [`content/${CONTAINER}.pak`]: bank(99) }), "forbidden_file");
  rejects(withBanks({ [`content/${CONTAINER}/99.pak`]: bank(99) }), "forbidden_file");
});

test("a bank goes in one place only", () => {
  for (const path of ["content/99.bnk", "map/99.bnk", "99.bnk", `content/${CONTAINER}/x/99.bnk`,
    `content/${CONTAINER}/name.bnk`, `content/${CONTAINER}/099.bnk`, `content/${CONTAINER}/99.BNK`,
    `content/${CONTAINER}/99999999999.bnk`, "content/a.b/99.bnk"]) {
    rejects(withBanks({ [path]: bank(99) }), "forbidden_file");
  }
});

test("a bank needs a container in the archive", () => {
  rejects(withBanks({ "content/other/99.bnk": bank(99) }), "bank_no_container");
});

test("a shipped bank is refused", () => {
  rejects(withBanks({ [`content/${CONTAINER}/${WARTHOG}.bnk`]: bank(WARTHOG) }), "shipped_bank");
});

test("the name and the header must agree", () => {
  rejects(withBanks({ [`content/${CONTAINER}/98.bnk`]: bank(99) }), "bad_bank");
});

test("what is not a bank is refused, empty included", () => {
  const name = `content/${CONTAINER}/99.bnk`;
  for (const body of [new TextEncoder().encode("BKHD lies"), new Uint8Array(0)]) {
    rejects(withBanks({ [name]: body }), "bad_bank");
  }
});

test("a bank's sections are held to their bounds", () => {
  const at = (b: Uint8Array, tag: string) => Buffer.from(b).indexOf(tag);
  const write = (b: Uint8Array, offset: number, value: number) =>
    new DataView(b.buffer).setUint32(offset, value, true);

  assert.equal(checkBank(99, bank(99)), null);
  let b = bank(99);
  write(b, at(b, "HIRC") + 4, 0xffffffff);
  assert.match(checkBank(99, b) ?? "", /past the end/);
  b = bank(99);
  write(b, at(b, "DIDX") + 16, 6);
  assert.match(checkBank(99, b) ?? "", /past DATA/);
  b = bank(99);
  write(b, at(b, "HIRC") + 8 + 4 + 1, 999);
  assert.match(checkBank(99, b) ?? "", /HIRC/);
  b = bank(99);
  write(b, 8, 149);
  assert.match(checkBank(99, b) ?? "", /version 150/);

  const twice = (tail: Uint8Array) => {
    const out = new Uint8Array(bank(99).length + tail.length);
    out.set(bank(99));
    out.set(tail, bank(99).length);
    return out;
  };
  assert.match(checkBank(99, twice(new TextEncoder().encode("FXPR\0\0\0\0"))) ?? "", /kind/);
  const whole = bank(99);
  assert.match(checkBank(99, twice(whole.subarray(at(whole, "HIRC")))) ?? "", /second/);
});

test("too many banks, and banks past the caps, stop the scan", () => {
  const many: Record<string, Uint8Array> = {};
  for (let id = 1000; id < 1033; id++) many[`content/${CONTAINER}/${id}.bnk`] = bank(id);
  rejects(withBanks(many), "too_many_banks");

  const big = new Uint8Array(MAX_BANK_BYTES + 1);
  const scan = scanArchive(zipSync(withBanks({ [`content/${CONTAINER}/99.bnk`]: big })));
  assert.equal(scan.verdict, "fail");
  assert.match(JSON.stringify(scan.findings), /bank size limit/);

  const full: Record<string, Uint8Array> = {};
  for (let id = 1; id <= 4; id++) full[`content/${CONTAINER}/${id}.bnk`] = new Uint8Array(MAX_BANK_BYTES - 1);
  const all = scanArchive(zipSync(withBanks(full)));
  assert.equal(all.verdict, "fail");
  assert.match(JSON.stringify(all.findings), /bank size limit/);
});

test("a new author's banks wait for a moderator, whatever the release's type", () => {
  const author = { role: "user", trust_level: 0 };
  const map = { map: true, banks: 0 };
  const mapWithBanks = { map: true, banks: 2 };
  const contentWithBanks = { map: false, banks: 1 };
  const plainContent = { map: false, banks: 0 };
  for (const carries of [map, mapWithBanks, contentWithBanks]) {
    assert.equal(needsReview(carries, author), true);
    assert.equal(needsReview(carries, { role: "user" }), true);
    assert.equal(needsReview(carries, { role: "user", trust_level: 1 }), true);
    assert.equal(needsReview(carries, { role: "user", trust_level: 2 }), false);
    assert.equal(needsReview(carries, { role: "moderator" }), false);
    assert.equal(needsReview(carries, { role: "admin" }), false);
  }
  assert.equal(needsReview(plainContent, author), false);
});

test("maps without baked water retain their existing acceptance", () => {
  assert.equal(scanArchive(zipSync(fixture(false))).verdict, "pass");
});

test("a complete declared Flux bake passes whole and streamed scans without retaining EXRs", async () => {
  const bytes = zipSync(fixture());
  const whole = scanArchive(bytes);
  assert.equal(whole.verdict, "pass", JSON.stringify(whole.findings));
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (let i = 0; i < bytes.length; i += 31) controller.enqueue(bytes.slice(i, i + 31));
      controller.close();
    },
  });
  const streamed = await scanArchiveStream(stream, bytes.length);
  assert.deepEqual(streamed.scan, whole);
  assert.equal(streamed.sha256, createHash("sha256").update(bytes).digest("hex"));
  for (const name of ["map/flux_state/height.exr", "map/flux_state/velocity.exr"]) {
    assert.equal(whole.files[name], undefined);
    assert.equal(whole.sizes[name], texture.length);
    assert.equal(whole.hashes[name], createHash("sha256").update(texture).digest("hex"));
  }
});

test("EXRs outside the exact Flux texture names stay forbidden", () => {
  for (const path of ["preview.exr", "content/height.exr", "map/other.exr",
    "map/flux_state/extra.exr", "map/flux_state/nested/height.exr", "map/flux_state/HEIGHT.EXR"]) {
    const members = fixture();
    members[path] = texture;
    rejects(members, "forbidden_file");
  }
});

test("a content release cannot use the map-only EXR exception", () => {
  const members = fixture();
  members["mjolnir.json"] = json({ schema_version: 1, name: "Content", version: "1.0.0", type: "content" });
  rejects(members, "forbidden_file");
});

test("undeclared or unsafe baked-water paths do not authorize EXRs", () => {
  for (const flux of [{}, { state: {} }, { state: "flux_state" },
    { state: { ...state, height: "../height.exr" } }]) {
    const members = fixture();
    members["map/level.json"] = json({ flux });
    rejects(members, "bad_flux_state");
    rejects(members, "forbidden_file");
  }
});

test("a declared bake cannot silently omit either texture", () => {
  for (const name of ["height", "velocity"]) {
    for (const empty of [true, false]) {
      const members = fixture();
      if (empty) members[`map/flux_state/${name}.exr`] = new Uint8Array(0);
      else delete members[`map/flux_state/${name}.exr`];
      rejects(members, "flux_file_missing");
    }
  }
});

test("bake metadata must be present, valid, and match the level", () => {
  for (const metadata of [undefined, new TextEncoder().encode("broken"), json({ ...state, res: [1, 1] })]) {
    const members = fixture();
    if (metadata) members["map/flux_state/state.json"] = metadata;
    else delete members["map/flux_state/state.json"];
    rejects(members, "bad_flux_state");
  }
});

test("invalid bake dimensions are rejected", () => {
  for (const invalid of [{ ...state, centre: [1, 2] }, { ...state, res: [0, 160] },
    { ...state, res: [192.5, 160] }, { ...state, cell: -1 }, { ...state, height_cm: 0 }]) {
    const members = fixture();
    members["map/level.json"] = json({ flux: { state: invalid } });
    members["map/flux_state/state.json"] = json(invalid);
    rejects(members, "bad_flux_state");
  }
});

test("a Flux-labelled archive still rejects traversal and executable payloads", () => {
  for (const path of ["map/flux_state/../height.exr", "map/flux_state/evil.dll"]) {
    const members = fixture();
    members[path] = texture;
    rejects(members, "forbidden_file");
    if (path.includes("..")) rejects(members, "path_traversal");
  }
});

function namedFluxFixture() {
  const members = fixture(false);
  const provenance = {
    schema: "mjolnir-flux-provenance-v1", terrain_manifest_sha256: "1".repeat(64),
    terrain_samples_sha256: "2".repeat(64), water_geometry_sha256: "3".repeat(64),
    capture_bed_sha256: "4".repeat(64), settings_sha256: "5".repeat(64),
  };
  const domains = ["upper_river", "lower_lake"].map((id) => {
    const domain = { centre: [0, 0, 29500], res: [1024, 512], cell: 97.65625, height: 28200 };
    const digest = createHash("sha256").update(texture).digest("hex");
    const namedState = {
      schema: "mjolnir-flux-state-v2", centre: domain.centre, res: domain.res,
      cell: domain.cell, height_cm: domain.height, capture: 8350, origin: [0, 0, 0], provenance,
      height: `flux_state/${id}/height.exr`, velocity: `flux_state/${id}/velocity.exr`,
      ground: `flux_state/${id}/ground.exr`,
      height_sha256: digest, velocity_sha256: digest, ground_sha256: digest,
    };
    members[`map/flux_state/${id}/state.json`] = json(namedState);
    for (const key of ["height", "velocity", "ground"] as const) members[`map/${namedState[key]}`] = texture;
    return { id, playback: "baked", domain, provenance, state: namedState };
  });
  const level = { flux: { schema: "mjolnir-flux-v2", domains } };
  members["map/level.json"] = json(level);
  return { members, level };
}

test("multiple baked Flux domains retain all six streamed textures", async () => {
  const { members } = namedFluxFixture(), bytes = zipSync(members);
  const whole = scanArchive(bytes);
  assert.equal(whole.verdict, "pass", JSON.stringify(whole.findings));
  const streamed = await scanArchiveStream(new ReadableStream({ start(c) { c.enqueue(bytes); c.close(); } }), bytes.length);
  assert.deepEqual(streamed.scan, whole);
  for (const id of ["upper_river", "lower_lake"]) {
    for (const key of ["height", "velocity", "ground"]) {
      const name = `map/flux_state/${id}/${key}.exr`;
      assert.equal(whole.files[name], undefined);
      assert.equal(whole.sizes[name], texture.length);
      assert.equal(whole.hashes[name], createHash("sha256").update(texture).digest("hex"));
    }
  }
});

test("named Flux cannot omit or empty any of its three state textures", () => {
  for (const key of ["height", "velocity", "ground"]) {
    for (const empty of [false, true]) {
      const { members } = namedFluxFixture(), name = `map/flux_state/upper_river/${key}.exr`;
      if (empty) members[name] = new Uint8Array(0); else delete members[name];
      rejects(members, "flux_file_missing");
    }
  }
});

test("named Flux sidecars and optional texture seals must match", () => {
  for (const mutation of ["missing", "different", "texture"]) {
    const { members, level } = namedFluxFixture();
    if (mutation === "missing") delete members["map/flux_state/upper_river/state.json"];
    if (mutation === "different") members["map/flux_state/upper_river/state.json"] = json({ ...level.flux.domains[0].state, capture: 1 });
    if (mutation === "texture") members["map/flux_state/upper_river/ground.exr"] = new Uint8Array([1, 2]);
    rejects(members, "bad_flux_state");
  }
});

test("named Flux rejects authoring playback, duplicate ids and unsafe paths", () => {
  for (const mutate of [
    (level: ReturnType<typeof namedFluxFixture>["level"]) => { level.flux.domains[0].playback = "simulate"; },
    (level: ReturnType<typeof namedFluxFixture>["level"]) => { level.flux.domains.push(level.flux.domains[0]); },
    (level: ReturnType<typeof namedFluxFixture>["level"]) => { level.flux.domains[0].id = "../upper_river"; },
    (level: ReturnType<typeof namedFluxFixture>["level"]) => { level.flux.domains[0].id = "UPPER"; },
    (level: ReturnType<typeof namedFluxFixture>["level"]) => { level.flux.domains[0].state.ground = "flux_state/lower_lake/ground.exr"; },
    (level: ReturnType<typeof namedFluxFixture>["level"]) => { level.flux.domains[0].state.height = "flux_state/../height.exr"; },
  ]) {
    const { members, level } = namedFluxFixture(); mutate(level); members["map/level.json"] = json(level);
    rejects(members, "bad_flux_state");
  }
});

test("named Flux validates domain fit, origin and terrain provenance", () => {
  for (const mutate of [
    (s: ReturnType<typeof namedFluxFixture>["level"]["flux"]["domains"][number]) => { s.state.centre = [0, 0, 29502]; },
    (s: ReturnType<typeof namedFluxFixture>["level"]["flux"]["domains"][number]) => { s.state.origin = [1, 0, 0]; },
    (s: ReturnType<typeof namedFluxFixture>["level"]["flux"]["domains"][number]) => { s.state.res = [192, 512]; },
    (s: ReturnType<typeof namedFluxFixture>["level"]["flux"]["domains"][number]) => { s.state.provenance = { ...s.provenance, settings_sha256: "6".repeat(64) }; },
  ]) {
    const { members, level } = namedFluxFixture(); mutate(level.flux.domains[0]);
    members["map/level.json"] = json(level);
    members["map/flux_state/upper_river/state.json"] = json(level.flux.domains[0].state);
    rejects(members, "bad_flux_state");
  }
});

test("named Flux does not authorize undeclared textures or general EXRs", () => {
  for (const name of ["map/flux_state/upper_river/extra.exr", "map/flux_state/third/height.exr", "preview.exr"]) {
    const { members } = namedFluxFixture(); members[name] = texture;
    rejects(members, "forbidden_file");
  }
});
