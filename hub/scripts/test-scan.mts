import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";
import { zipSync } from "fflate";

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
