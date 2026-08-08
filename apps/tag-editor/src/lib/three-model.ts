import * as THREE from "three";
import type { ModelGeometry } from "./api";

/** Surface flag bit 1: collision the player never sees. */
export const FLAG_INVISIBLE = 1 << 1;

export const IDENTITY = new THREE.Matrix4();
const ONE = new THREE.Vector3(1, 1, 1);

export function quat(q: [number, number, number, number]): THREE.Quaternion {
  return new THREE.Quaternion(q[0], q[1], q[2], q[3]).normalize();
}

/** Rest-pose world matrix per skeleton node. Parents precede children in
 *  Halo node arrays, so one forward pass composes the chain. */
export function nodeWorlds(nodes: ModelGeometry["nodes"]): THREE.Matrix4[] {
  const worlds: THREE.Matrix4[] = [];
  nodes.forEach((n, i) => {
    const local = new THREE.Matrix4().compose(
      new THREE.Vector3(...n.translation),
      quat(n.rotation),
      ONE,
    );
    worlds[i] =
      n.parent >= 0 && n.parent < i ? worlds[n.parent].clone().multiply(local) : local;
  });
  return worlds;
}

export function hueOf(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return (h % 360) / 360;
}

/**
 * An object's collision shell, posed by its skeleton, as one group in tag
 * space. Invisible-flagged surfaces are left out — a proxy in the scenario
 * view wants the object's visible shape.
 */
export function buildModelGroup(
  geometry: ModelGeometry,
  material: THREE.Material,
): THREE.Group {
  const group = new THREE.Group();
  const worlds = nodeWorlds(geometry.nodes);
  for (const m of geometry.meshes) {
    const world = m.node >= 0 && m.node < worlds.length ? worlds[m.node] : IDENTITY;
    const idx: number[] = [];
    for (let t = 0; t * 3 < m.indices.length; t++) {
      if (((m.flags[t] ?? 0) & FLAG_INVISIBLE) === 0) {
        idx.push(m.indices[t * 3], m.indices[t * 3 + 1], m.indices[t * 3 + 2]);
      }
    }
    if (idx.length === 0) continue;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(m.positions, 3));
    geo.setIndex(idx);
    const mesh = new THREE.Mesh(geo, material);
    mesh.applyMatrix4(world);
    group.add(mesh);
  }
  return group;
}

/** Dispose every geometry (not materials) under a group. */
export function disposeGeometries(root: THREE.Object3D) {
  root.traverse((o) => {
    if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments || o instanceof THREE.Points) {
      o.geometry.dispose();
    }
  });
}

// ---------------------------------------------------------------------------
// The packed sbsp world (see geometry.rs `sbsp_world` for the format).

/** One drawable collision mesh: geometry with one group per material, and the
 *  material key for each group — a collision-material index, or "invisible"
 *  for surfaces the player never sees. */
export type SbspMesh = {
  geometry: THREE.BufferGeometry;
  groups: (number | "invisible")[];
};

export type SbspWorld = {
  /** One mesh per instanced-geometry definition; empty defs are null. */
  defs: (SbspMesh | null)[];
  world: SbspMesh | null;
  instances: { def: number; matrix: THREE.Matrix4 }[];
};

export function parseSbspWorld(buffer: ArrayBuffer): SbspWorld {
  const view = new DataView(buffer);
  if (view.getUint32(0, true) !== 0x50534253) {
    throw new Error("not an SBSP payload");
  }
  const jsonLen = view.getUint32(4, true);
  const header = JSON.parse(
    new TextDecoder().decode(new Uint8Array(buffer, 8, jsonLen)),
  ) as {
    defs: { verts: number; tris: number }[];
    world: { verts: number; tris: number } | null;
    instances: number;
  };
  let at = 8 + jsonLen;
  at += (4 - (at % 4)) % 4;

  const readMesh = (counts: { verts: number; tris: number }) => {
    const positions = new Float32Array(buffer, at, counts.verts * 3);
    at += counts.verts * 12;
    const indices = new Uint32Array(buffer, at, counts.tris * 3);
    at += counts.tris * 12;
    // Surface flags low half, collision-material index high half.
    const flags = new Uint32Array(buffer, at, counts.tris);
    at += counts.tris * 4;
    return { positions, indices, flags };
  };

  // Bucket triangles by material so each bucket becomes a geometry group and
  // can carry its own tint. Invisible surfaces get one bucket of their own,
  // toggled globally through their shared material's `visible`.
  const build = (m: ReturnType<typeof readMesh>, tris: number): SbspMesh => {
    const buckets = new Map<number | "invisible", number[]>();
    for (let t = 0; t < tris; t++) {
      const key: number | "invisible" =
        (m.flags[t] & FLAG_INVISIBLE) !== 0 ? "invisible" : m.flags[t] >>> 16;
      let bucket = buckets.get(key);
      if (!bucket) {
        bucket = [];
        buckets.set(key, bucket);
      }
      bucket.push(m.indices[t * 3], m.indices[t * 3 + 1], m.indices[t * 3 + 2]);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(m.positions.slice(), 3));
    const index = new Uint32Array([...buckets.values()].reduce((n, b) => n + b.length, 0));
    const groups: (number | "invisible")[] = [];
    let start = 0;
    let slot = 0;
    for (const [key, bucket] of buckets) {
      index.set(bucket, start);
      geometry.addGroup(start, bucket.length, slot);
      groups.push(key);
      start += bucket.length;
      slot++;
    }
    geometry.setIndex(new THREE.BufferAttribute(index, 1));
    return { geometry, groups };
  };

  const defs: (SbspMesh | null)[] = [];
  for (const counts of header.defs) {
    if (counts.tris === 0) {
      defs.push(null);
      continue;
    }
    defs.push(build(readMesh(counts), counts.tris));
  }

  let world: SbspMesh | null = null;
  if (header.world && header.world.tris > 0) {
    world = build(readMesh(header.world), header.world.tris);
  }

  const instances: SbspWorld["instances"] = [];
  const f = new DataView(buffer, at);
  for (let i = 0; i < header.instances; i++) {
    const base = i * 56;
    const def = f.getUint32(base, true);
    const scale = f.getFloat32(base + 4, true);
    const v = (o: number) =>
      new THREE.Vector3(
        f.getFloat32(base + o, true),
        f.getFloat32(base + o + 4, true),
        f.getFloat32(base + o + 8, true),
      );
    // Basis vectors scaled by hand: Matrix4 has no uniform-scale helper
    // that leaves the translation column alone.
    const matrix = new THREE.Matrix4().makeBasis(
      v(8).multiplyScalar(scale),
      v(20).multiplyScalar(scale),
      v(32).multiplyScalar(scale),
    );
    matrix.setPosition(v(44));
    instances.push({ def, matrix });
  }
  return { defs, world, instances };
}
