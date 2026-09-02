import * as THREE from "three";
import { api, type MeshHeader, type RenderMeshRef } from "./api";

/** Unreal centimetres per Blam world unit (1 wu = 10 feet). Verified against
 *  the elite: 236 cm of SK_Elite_Common_Body over a 0.79 wu collision shell. */
export const CM_PER_WU = 304.8;

export type RenderMeshData = {
  header: MeshHeader;
  geometry: THREE.BufferGeometry;
};

/**
 * Parse a `read_mesh` payload into tag-space geometry: Unreal centimetres
 * scaled to world units and Y mirrored — the engine negates Y between the
 * Blam simulation and the Unreal world, so a mesh drawn among tag data has to
 * mirror back. Materials use DoubleSide throughout, so the flipped winding
 * the mirror causes needs no index rewrite.
 */
export function parseMeshPayload(buffer: ArrayBuffer): RenderMeshData {
  const view = new DataView(buffer);
  if (view.getUint32(0, true) !== 0x48534d55) {
    throw new Error("not a mesh payload");
  }
  const jsonLen = view.getUint32(4, true);
  const header = JSON.parse(
    new TextDecoder().decode(new Uint8Array(buffer, 8, jsonLen)),
  ) as MeshHeader;
  let at = 8 + jsonLen;
  at += (4 - (at % 4)) % 4;
  const verts = header.verts;
  const tris = header.tris;
  const positions = new Float32Array(buffer, at, verts * 3);
  at += verts * 12;
  const normals = new Float32Array(buffer, at, verts * 3);
  at += verts * 12;
  const uvs = new Float32Array(buffer, at, verts * 2);
  at += verts * 8;
  const indices = new Uint32Array(buffer, at, tris * 3);

  const pos = new Float32Array(verts * 3);
  const nrm = new Float32Array(verts * 3);
  for (let v = 0; v < verts; v++) {
    pos[v * 3] = positions[v * 3] / CM_PER_WU;
    pos[v * 3 + 1] = -positions[v * 3 + 1] / CM_PER_WU;
    pos[v * 3 + 2] = positions[v * 3 + 2] / CM_PER_WU;
    nrm[v * 3] = normals[v * 3];
    nrm[v * 3 + 1] = -normals[v * 3 + 1];
    nrm[v * 3 + 2] = normals[v * 3 + 2];
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(nrm, 3));
  geometry.setAttribute("uv", new THREE.BufferAttribute(uvs.slice(), 2));
  geometry.setIndex(new THREE.BufferAttribute(indices.slice(), 1));
  for (const s of header.sections) {
    geometry.addGroup(
      s.first_index,
      s.num_triangles * 3,
      Math.min(Math.max(s.material, 0), Math.max(header.materials.length - 1, 0)),
    );
  }
  if (header.sections.length === 0) {
    geometry.addGroup(0, tris * 3, 0);
  }
  return { header, geometry };
}

/** One material per slot: the material's own flat colour when it carries
 *  one, a placeholder tint otherwise; textures stream in over them. */
export function buildMeshMaterials(header: MeshHeader): THREE.MeshStandardMaterial[] {
  const materials = header.materials.map(
    (m, i) =>
      new THREE.MeshStandardMaterial({
        color: m.tint
          ? new THREE.Color().setRGB(m.tint[0], m.tint[1], m.tint[2], THREE.LinearSRGBColorSpace)
          : new THREE.Color().setHSL((i * 0.31) % 1, 0.12, 0.55),
        metalness: 0.05,
        roughness: 0.85,
        side: THREE.DoubleSide,
      }),
  );
  if (materials.length === 0) {
    materials.push(
      new THREE.MeshStandardMaterial({ color: 0x9aa2ab, side: THREE.DoubleSide }),
    );
  }
  return materials;
}

/** Data-URI cache so one texture decodes once per viewer, not per instance. */
export type TextureCache = Map<number, Promise<string | null>>;

/** Stream each resolved base-colour texture onto its slot's material. */
export function streamMeshTextures(
  header: MeshHeader,
  materials: THREE.MeshStandardMaterial[],
  cache: TextureCache,
  isAlive: () => boolean,
) {
  header.materials.forEach((m, i) => {
    if (m.texture === null || i >= materials.length) return;
    let png = cache.get(m.texture);
    if (!png) {
      png = api
        .readTexture(m.texture)
        .then((t) => t.png)
        .catch(() => null);
      cache.set(m.texture, png);
    }
    void png.then((uri) => {
      if (!uri || !isAlive()) return;
      new THREE.TextureLoader().load(uri, (texture) => {
        if (!isAlive()) {
          texture.dispose();
          return;
        }
        texture.flipY = false;
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.wrapS = THREE.RepeatWrapping;
        texture.wrapT = THREE.RepeatWrapping;
        materials[i].map = texture;
        materials[i].color.set(0xffffff);
        materials[i].needsUpdate = true;
      });
    });
  });
}

/** An Unreal Rotator (pitch, yaw, roll — degrees) as a tag-space quaternion:
 *  UE's own rotator-to-quat, then conjugated by the Y mirror. */
function rotatorToTagQuat(r: [number, number, number]): THREE.Quaternion {
  const h = Math.PI / 360; // degrees to half-radians
  const sp = Math.sin(r[0] * h);
  const cp = Math.cos(r[0] * h);
  const sy = Math.sin(r[1] * h);
  const cy = Math.cos(r[1] * h);
  const sr = Math.sin(r[2] * h);
  const cr = Math.cos(r[2] * h);
  const x = cr * sp * sy - sr * cp * cy;
  const y = -cr * sp * cy - sr * cp * sy;
  const z = cr * cp * sy - sr * sp * cy;
  const w = cr * cp * cy + sr * sp * sy;
  // Mirroring Y flips the handedness: axis components in the mirror plane
  // negate, the one along the mirror normal stays.
  return new THREE.Quaternion(-x, y, -z, w);
}

/** The component transform placing one mesh in tag space. */
export function componentMatrix(ref: RenderMeshRef): THREE.Matrix4 {
  // Mirroring Y flips the handedness: quaternion components in the mirror
  // plane negate, the one along the mirror normal stays.
  const rotation = ref.quat
    ? new THREE.Quaternion(-ref.quat[0], ref.quat[1], -ref.quat[2], ref.quat[3])
    : rotatorToTagQuat(ref.rotation);
  return new THREE.Matrix4().compose(
    new THREE.Vector3(
      ref.location[0] / CM_PER_WU,
      -ref.location[1] / CM_PER_WU,
      ref.location[2] / CM_PER_WU,
    ),
    rotation,
    new THREE.Vector3(...ref.scale),
  );
}

/** Geometry-and-materials cache keyed by mesh catalog index, so a mesh used
 *  by many placements decodes once and every instance shares its materials. */
export type MeshCache = Map<
  number,
  Promise<{ data: RenderMeshData; materials: THREE.MeshStandardMaterial[] } | null>
>;

/**
 * Load an object's render model — every reachable mesh, placed by its
 * component transform — as one tag-space group. Meshes that fail to read
 * (skeletal-Nanite placeholders, unparsed formats) are skipped. Fallback
 * refs (MeshSynchronization stand-ins) load only when no Blueprint-bound
 * mesh was readable. Null when nothing at all could be drawn.
 */
export async function loadRenderGroup(
  refs: RenderMeshRef[],
  meshes: MeshCache,
  textures: TextureCache,
  isAlive: () => boolean,
): Promise<THREE.Group | null> {
  const load = async (group: THREE.Group, subset: RenderMeshRef[]) => {
    let maxTris = 0;
    await Promise.all(
      subset.map(async (ref) => {
        let entry = meshes.get(ref.mesh);
        if (!entry) {
          entry = api
            .readMesh(ref.mesh)
            .then((buffer) => {
              const data = parseMeshPayload(buffer);
              const materials = buildMeshMaterials(data.header);
              streamMeshTextures(data.header, materials, textures, isAlive);
              return { data, materials };
            })
            .catch(() => null);
          meshes.set(ref.mesh, entry);
        }
        const loaded = await entry;
        if (!loaded) return;
        const mesh = new THREE.Mesh(loaded.data.geometry, loaded.materials);
        mesh.applyMatrix4(componentMatrix(ref));
        group.add(mesh);
        maxTris = Math.max(maxTris, loaded.data.header.tris);
      }),
    );
    return maxTris;
  };
  const group = new THREE.Group();
  const primaryTris = await load(group, refs.filter((r) => !r.fallback));
  // A Blueprint sometimes binds only helper meshes a few triangles big
  // (anim-dynamics proxies); those do not count as a drawable body.
  if (primaryTris <= 16) {
    await load(group, refs.filter((r) => r.fallback));
  }
  return group.children.length > 0 ? group : null;
}
