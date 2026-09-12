import { save } from "@tauri-apps/plugin-dialog";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { api, type MeshHeader } from "../lib/api";
import { useEditor } from "../stores/editor-store";

/**
 * The Unreal mesh viewer: a cooked StaticMesh with its real textures.
 *
 * What renders is the classic LOD chain the cook kept. LOD0 of most meshes
 * was replaced by Nanite cluster data this reader does not decode, so the
 * geometry shown is the Nanite fallback — right shape and materials, reduced
 * density. The header says which LOD it is.
 */
export function MeshViewer() {
  const exportMesh = useEditor((s) => s.exportMesh);
  const meshName = useEditor((s) => {
    const tab = s.tabs.find((t) => t.id === s.activeTab);
    return tab?.label ?? "mesh";
  });
  const [wrote, setWrote] = useState<string | null>(null);
  async function onExport() {
    const dest = await save({
      defaultPath: `${meshName.replace(/\.[^.]*$/, "")}.glb`,
      filters: [{ name: "glTF binary", extensions: ["glb"] }],
    });
    if (!dest) return;
    setWrote(null);
    const written = await exportMesh(dest);
    if (written !== null) setWrote(`wrote ${written.toLocaleString()} bytes`);
  }

  const index = useEditor((s) => s.selectedMesh);
  const [header, setHeader] = useState<MeshHeader | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<ArrayBuffer | null>(null);
  const [wireframe, setWireframe] = useState(false);
  const [textured, setTextured] = useState(true);

  useEffect(() => {
    if (index === null) return;
    let stale = false;
    setHeader(null);
    setPayload(null);
    setError(null);
    api
      .readMesh(index)
      .then((buffer) => {
        if (stale) return;
        const view = new DataView(buffer);
        if (view.getUint32(0, true) !== 0x48534d55) {
          throw new Error("not a mesh payload");
        }
        const jsonLen = view.getUint32(4, true);
        const parsed = JSON.parse(
          new TextDecoder().decode(new Uint8Array(buffer, 8, jsonLen)),
        ) as MeshHeader;
        setHeader(parsed);
        setPayload(buffer);
      })
      .catch((e) => {
        if (!stale) setError(String(e));
      });
    return () => {
      stale = true;
    };
  }, [index]);

  if (error) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center px-8 text-center">
        <p className="max-w-lg text-sm text-accent-red">{error}</p>
      </div>
    );
  }
  if (!header || !payload) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-dim">
        Reading mesh…
      </div>
    );
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-border-subtle px-4 py-2">
        <button
          type="button"
          onClick={() => setTextured(!textured)}
          aria-pressed={textured}
          className={`border px-1.5 py-0.5 font-mono text-[10px] ${
            textured
              ? "border-mjolnir-gold/60 bg-mjolnir-gold/10 text-mjolnir-gold"
              : "border-border-subtle text-text-dim hover:bg-surface-hover"
          }`}
        >
          textured
        </button>
        <button
          type="button"
          onClick={() => setWireframe(!wireframe)}
          aria-pressed={wireframe}
          className={`border px-1.5 py-0.5 font-mono text-[10px] ${
            wireframe
              ? "border-mjolnir-gold/60 bg-mjolnir-gold/10 text-mjolnir-gold"
              : "border-border-subtle text-text-dim hover:bg-surface-hover"
          }`}
        >
          wireframe
        </button>
        <button
          type="button"
          onClick={() => void onExport()}
          title="Write this mesh as glTF binary: every LOD, a primitive per material slot, metres and +Y up"
          className="border border-border-subtle px-1.5 py-0.5 font-mono text-[10px] text-text-dim hover:bg-surface-hover hover:text-mjolnir-gold"
        >
          export .glb…
        </button>
        {wrote && <span className="font-mono text-[10px] text-accent-green">{wrote}</span>}
        <span className="ml-auto font-mono text-[10px] text-text-dim">
          {header.verts.toLocaleString()} verts · {header.tris.toLocaleString()} tris ·{" "}
          {header.nanite ? "Nanite, full detail" : `LOD ${header.lod}${header.lod > 0 ? " (Nanite fallback)" : ""}`}
        </span>
      </div>
      <MeshScene header={header} payload={payload} wireframe={wireframe} textured={textured} />
      <div className="border-t border-border-subtle px-4 py-1.5 font-mono text-[10px] text-text-dim">
        {header.materials.length === 0 && "no materials"}
        {header.materials.map((m, i) => (
          <span key={i} className="mr-3">
            {m.slot || `slot ${i}`} →{" "}
            {m.texture_path
              ? m.texture_path.split("/").pop()
              : m.material_path
                ? `${m.material_path.split("/").pop()} (no base colour found)`
                : "unresolved"}
          </span>
        ))}
      </div>
    </div>
  );
}

function MeshScene(props: {
  header: MeshHeader;
  payload: ArrayBuffer;
  wireframe: boolean;
  textured: boolean;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const materialsRef = useRef<THREE.MeshStandardMaterial[]>([]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xd8dde5, 0x3a3f46, 1.9));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(3, 6, 2);
    scene.add(sun);

    const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    // Unpack the payload: header, then positions, normals, uvs, indices.
    const view = new DataView(props.payload);
    const jsonLen = view.getUint32(4, true);
    let at = 8 + jsonLen;
    at += (4 - (at % 4)) % 4;
    const verts = props.header.verts;
    const tris = props.header.tris;
    const positions = new Float32Array(props.payload, at, verts * 3);
    at += verts * 12;
    const normals = new Float32Array(props.payload, at, verts * 3);
    at += verts * 12;
    const uvs = new Float32Array(props.payload, at, verts * 2);
    at += verts * 8;
    const indices = new Uint32Array(props.payload, at, tris * 3);

    // Unreal is Z-up left-handed in centimetres; swapping y/z gives three's
    // right-handed Y-up and flips the winding back to front-facing.
    const pos = new Float32Array(verts * 3);
    const nrm = new Float32Array(verts * 3);
    for (let v = 0; v < verts; v++) {
      pos[v * 3] = positions[v * 3];
      pos[v * 3 + 1] = positions[v * 3 + 2];
      pos[v * 3 + 2] = positions[v * 3 + 1];
      nrm[v * 3] = normals[v * 3];
      nrm[v * 3 + 1] = normals[v * 3 + 2];
      nrm[v * 3 + 2] = normals[v * 3 + 1];
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geometry.setAttribute("normal", new THREE.BufferAttribute(nrm, 3));
    geometry.setAttribute("uv", new THREE.BufferAttribute(uvs.slice(), 2));
    geometry.setIndex(new THREE.BufferAttribute(indices.slice(), 1));

    // One material per section's material index: the material's own flat
    // colour when it carries one, a placeholder otherwise; textures stream
    // in after.
    const materials: THREE.MeshStandardMaterial[] = props.header.materials.map(
      (m, i) =>
        new THREE.MeshStandardMaterial({
          color: m.tint
            ? new THREE.Color().setRGB(m.tint[0], m.tint[1], m.tint[2], THREE.LinearSRGBColorSpace)
            : new THREE.Color().setHSL((i * 0.31) % 1, 0.2, 0.6),
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
    materialsRef.current = materials;
    for (const s of props.header.sections) {
      geometry.addGroup(
        s.first_index,
        s.num_triangles * 3,
        Math.min(Math.max(s.material, 0), materials.length - 1),
      );
    }
    if (props.header.sections.length === 0) {
      geometry.addGroup(0, tris * 3, 0);
    }

    const mesh = new THREE.Mesh(geometry, materials);
    scene.add(mesh);

    let alive = true;
    props.header.materials.forEach((m, i) => {
      if (m.texture === null) return;
      void api
        .readTexture(m.texture)
        .then((t) => {
          if (!alive) return;
          new THREE.TextureLoader().load(t.png, (texture) => {
            if (!alive) return;
            texture.flipY = false;
            texture.colorSpace = THREE.SRGBColorSpace;
            texture.wrapS = THREE.RepeatWrapping;
            texture.wrapT = THREE.RepeatWrapping;
            materials[i].map = texture;
            materials[i].color.set(0xffffff);
            materials[i].needsUpdate = true;
          });
        })
        .catch(() => {
          // The tint stays; the footer already says what resolved.
        });
    });

    const bounds = new THREE.Box3().setFromObject(mesh);
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3()).length() || 1;
    camera.position.copy(center).add(new THREE.Vector3(0.8, 0.5, 0.8).multiplyScalar(size));
    camera.near = size / 500;
    camera.far = size * 50;
    camera.updateProjectionMatrix();
    controls.target.copy(center);

    const grid = new THREE.GridHelper(size * 2, 20, 0x444a52, 0x2a2e34);
    grid.position.y = bounds.min.y;
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.4;
    scene.add(grid);

    let frame = 0;
    const draw = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);

    const resize = new ResizeObserver(() => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      if (w === 0 || h === 0) return;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    });
    resize.observe(mount);

    return () => {
      alive = false;
      cancelAnimationFrame(frame);
      resize.disconnect();
      controls.dispose();
      geometry.dispose();
      for (const m of materials) {
        m.map?.dispose();
        m.dispose();
      }
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.header, props.payload]);

  useEffect(() => {
    for (const m of materialsRef.current) {
      m.wireframe = props.wireframe;
      if (m.map) {
        // Toggling textured switches the map off without losing it.
        m.map.colorSpace = THREE.SRGBColorSpace;
      }
      m.needsUpdate = true;
    }
  }, [props.wireframe]);

  useEffect(() => {
    for (const m of materialsRef.current) {
      if (!m.userData.savedMap && m.map) m.userData.savedMap = m.map;
      const saved = m.userData.savedMap as THREE.Texture | undefined;
      if (props.textured && saved) {
        m.map = saved;
        m.color.set(0xffffff);
      } else if (!props.textured) {
        m.map = null;
        m.color.set(0x9aa2ab);
      }
      m.needsUpdate = true;
    }
  }, [props.textured]);

  return <div ref={mountRef} className="min-h-0 flex-1" />;
}
