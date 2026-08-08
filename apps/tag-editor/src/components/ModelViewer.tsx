import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { api, type ModelGeometry } from "../lib/api";
import { useEditor } from "../stores/editor-store";

/** Surface flag bit 1: collision the player never sees (ladders excepted). */
const FLAG_INVISIBLE = 1 << 1;

/**
 * The Model view: the object's simulation geometry in 3D.
 *
 * What it draws is the collision shell posed by the skeleton — the game ships
 * no render meshes in its tag data (visuals are Unreal packages), and the
 * collision model is the shape the simulation actually plays.
 */
export function ModelViewer() {
  const index = useEditor((s) => s.selectedTag);
  const [geometry, setGeometry] = useState<ModelGeometry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [wireframe, setWireframe] = useState(false);
  const [showSkeleton, setShowSkeleton] = useState(true);
  const [showMarkers, setShowMarkers] = useState(false);
  const [showInvisible, setShowInvisible] = useState(false);
  const [hiddenParts, setHiddenParts] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (index === null) return;
    let stale = false;
    setLoading(true);
    setError(null);
    setGeometry(null);
    setHiddenParts(new Set());
    api
      .readModelGeometry(index)
      .then((g) => {
        if (!stale) setGeometry(g);
      })
      .catch((e) => {
        if (!stale) setError(String(e));
      })
      .finally(() => {
        if (!stale) setLoading(false);
      });
    return () => {
      stale = true;
    };
  }, [index]);

  const parts = useMemo(() => {
    const seen = new Set<string>();
    for (const m of geometry?.meshes ?? []) {
      seen.add(partKey(m.region, m.permutation));
    }
    return [...seen];
  }, [geometry]);

  const stats = useMemo(() => {
    let verts = 0;
    let tris = 0;
    for (const m of geometry?.meshes ?? []) {
      verts += m.positions.length / 3;
      tris += m.indices.length / 3;
    }
    return { verts, tris };
  }, [geometry]);

  function togglePart(key: string) {
    setHiddenParts((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  if (loading) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-dim">
        Reading geometry…
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center px-8 text-center">
        <p className="max-w-lg text-sm text-accent-red">{error}</p>
      </div>
    );
  }
  if (!geometry) return <div className="min-h-0 flex-1" />;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-border-subtle px-4 py-2">
        <Toggle on={wireframe} onClick={() => setWireframe(!wireframe)} label="wireframe" />
        <Toggle
          on={showSkeleton}
          onClick={() => setShowSkeleton(!showSkeleton)}
          label={`skeleton · ${geometry.nodes.length}`}
          disabled={geometry.nodes.length === 0}
        />
        <Toggle
          on={showMarkers}
          onClick={() => setShowMarkers(!showMarkers)}
          label={`markers · ${geometry.marker_groups.reduce((n, g) => n + g.markers.length, 0)}`}
          disabled={geometry.marker_groups.length === 0}
        />
        <Toggle
          on={showInvisible}
          onClick={() => setShowInvisible(!showInvisible)}
          label="invisible surfaces"
          title="Collision the player never sees: ladders, kill volumes, projectile blockers"
        />
        <span className="ml-auto font-mono text-[10px] text-text-dim">
          {stats.verts.toLocaleString()} verts · {stats.tris.toLocaleString()} tris
        </span>
      </div>
      {parts.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5 border-b border-border-subtle px-4 py-1.5">
          {parts.map((p) => (
            <Toggle key={p} on={!hiddenParts.has(p)} onClick={() => togglePart(p)} label={p} />
          ))}
        </div>
      )}
      <Scene
        geometry={geometry}
        wireframe={wireframe}
        showSkeleton={showSkeleton}
        showMarkers={showMarkers}
        showInvisible={showInvisible}
        hiddenParts={hiddenParts}
      />
      <div className="border-t border-border-subtle px-4 py-1.5 font-mono text-[10px] text-text-dim">
        {geometry.collision ? (
          <>collision {geometry.collision}</>
        ) : (
          <span className="text-accent-red">no collision_model reachable — skeleton only</span>
        )}
        {" · "}
        {geometry.skeleton ? (
          <>skeleton {geometry.skeleton}</>
        ) : (
          <span className="text-accent-red">
            no skeleton_model reachable — pieces drawn unposed
          </span>
        )}
      </div>
    </div>
  );
}

function partKey(region: string, permutation: string): string {
  return permutation && permutation !== "default" ? `${region}/${permutation}` : region;
}

function Toggle(props: {
  on: boolean;
  onClick: () => void;
  label: string;
  title?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={props.onClick}
      title={props.title}
      disabled={props.disabled}
      aria-pressed={props.on}
      className={`border px-1.5 py-0.5 font-mono text-[10px] disabled:opacity-40 ${
        props.on
          ? "border-mjolnir-gold/60 bg-mjolnir-gold/10 text-mjolnir-gold"
          : "border-border-subtle text-text-dim hover:bg-surface-hover"
      }`}
    >
      {props.label}
    </button>
  );
}

/** One drawn piece, kept so the toggles can flip it without a scene rebuild. */
type DrawnMesh = {
  key: string;
  visible: THREE.Mesh;
  invisible: THREE.Mesh | null;
  materials: THREE.MeshStandardMaterial[];
};

function Scene(props: {
  geometry: ModelGeometry;
  wireframe: boolean;
  showSkeleton: boolean;
  showMarkers: boolean;
  showInvisible: boolean;
  hiddenParts: Set<string>;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const drawnRef = useRef<DrawnMesh[]>([]);
  const skeletonRef = useRef<THREE.Group | null>(null);
  const markersRef = useRef<THREE.Group | null>(null);

  // Renderer, camera and scene live for the mount; the model group is rebuilt
  // when the geometry changes.
  const threeRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    controls: OrbitControls;
    model: THREE.Group;
  } | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xbfc8d6, 0x33383f, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(3, 6, 2);
    scene.add(sun);
    const grid = new THREE.GridHelper(4, 16, 0x444a52, 0x2a2e34);
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.5;
    scene.add(grid);

    const camera = new THREE.PerspectiveCamera(50, 1, 0.001, 500);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    const model = new THREE.Group();
    // Tag space is Z-up; rotating the whole group maps (x, y, z) to the
    // (x, z, -y) three.js expects, so everything inside stays in tag space.
    model.rotation.x = -Math.PI / 2;
    scene.add(model);

    threeRef.current = { renderer, scene, camera, controls, model };

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
      cancelAnimationFrame(frame);
      resize.disconnect();
      controls.dispose();
      renderer.dispose();
      mount.removeChild(renderer.domElement);
      threeRef.current = null;
    };
  }, []);

  // Rebuild the model group when the geometry changes.
  useEffect(() => {
    const three = threeRef.current;
    if (!three) return;
    const { model, camera, controls } = three;

    disposeChildren(model);
    drawnRef.current = [];
    skeletonRef.current = null;
    markersRef.current = null;

    const g = props.geometry;
    const worlds = nodeWorlds(g.nodes);

    for (const m of g.meshes) {
      const world = m.node >= 0 && m.node < worlds.length ? worlds[m.node] : IDENTITY;
      const positions = new THREE.Float32BufferAttribute(m.positions, 3);
      const visIdx: number[] = [];
      const invIdx: number[] = [];
      for (let t = 0; t * 3 < m.indices.length; t++) {
        const target = (m.flags[t] ?? 0) & FLAG_INVISIBLE ? invIdx : visIdx;
        target.push(m.indices[t * 3], m.indices[t * 3 + 1], m.indices[t * 3 + 2]);
      }

      const color = new THREE.Color().setHSL(hueOf(m.region), 0.18, 0.62);
      const materials: THREE.MeshStandardMaterial[] = [];
      const buildMesh = (idx: number[], invisible: boolean) => {
        const geo = new THREE.BufferGeometry();
        geo.setAttribute("position", positions);
        geo.setIndex(idx);
        const mat = new THREE.MeshStandardMaterial({
          color: invisible ? 0xd06040 : color,
          transparent: invisible,
          opacity: invisible ? 0.4 : 1,
          flatShading: true,
          side: THREE.DoubleSide,
          metalness: 0.1,
          roughness: 0.85,
        });
        materials.push(mat);
        const mesh = new THREE.Mesh(geo, mat);
        mesh.applyMatrix4(world);
        model.add(mesh);
        return mesh;
      };

      drawnRef.current.push({
        key: partKey(m.region, m.permutation),
        visible: buildMesh(visIdx, false),
        invisible: invIdx.length > 0 ? buildMesh(invIdx, true) : null,
        materials,
      });
    }

    // Skeleton overlay: a line per parent link, a dot per joint.
    if (g.nodes.length > 0) {
      const overlay = new THREE.Group();
      const joints: number[] = [];
      const bones: number[] = [];
      g.nodes.forEach((n, i) => {
        const p = new THREE.Vector3().setFromMatrixPosition(worlds[i]);
        joints.push(p.x, p.y, p.z);
        if (n.parent >= 0 && n.parent < worlds.length) {
          const q = new THREE.Vector3().setFromMatrixPosition(worlds[n.parent]);
          bones.push(q.x, q.y, q.z, p.x, p.y, p.z);
        }
      });
      const boneGeo = new THREE.BufferGeometry();
      boneGeo.setAttribute("position", new THREE.Float32BufferAttribute(bones, 3));
      overlay.add(
        new THREE.LineSegments(
          boneGeo,
          new THREE.LineBasicMaterial({ color: 0xd8b64a, depthTest: false }),
        ),
      );
      const jointGeo = new THREE.BufferGeometry();
      jointGeo.setAttribute("position", new THREE.Float32BufferAttribute(joints, 3));
      overlay.add(
        new THREE.Points(
          jointGeo,
          new THREE.PointsMaterial({
            color: 0xf0d060,
            size: 5,
            sizeAttenuation: false,
            depthTest: false,
          }),
        ),
      );
      overlay.renderOrder = 1;
      model.add(overlay);
      skeletonRef.current = overlay;
    }

    // Markers: a small axis triad each.
    if (g.marker_groups.length > 0) {
      const overlay = new THREE.Group();
      for (const group of g.marker_groups) {
        for (const marker of group.markers) {
          const world =
            marker.node >= 0 && marker.node < worlds.length ? worlds[marker.node] : IDENTITY;
          const local = new THREE.Matrix4().compose(
            new THREE.Vector3(...marker.translation),
            quat(marker.rotation),
            ONE,
          );
          const axes = new THREE.AxesHelper(0.04);
          (axes.material as THREE.Material).depthTest = false;
          axes.applyMatrix4(world.clone().multiply(local));
          overlay.add(axes);
        }
      }
      overlay.renderOrder = 2;
      model.add(overlay);
      markersRef.current = overlay;
    }

    // Frame the camera on what was just built.
    const bounds = new THREE.Box3().setFromObject(model);
    if (!bounds.isEmpty()) {
      const center = bounds.getCenter(new THREE.Vector3());
      const size = bounds.getSize(new THREE.Vector3()).length() || 1;
      camera.position.copy(center).add(new THREE.Vector3(0.9, 0.55, 0.9).multiplyScalar(size));
      camera.near = size / 500;
      camera.far = size * 50;
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();
    }
  }, [props.geometry]);

  // Cheap toggles: no rebuild, just visibility and material flips.
  useEffect(() => {
    for (const d of drawnRef.current) {
      const shown = !props.hiddenParts.has(d.key);
      d.visible.visible = shown;
      if (d.invisible) d.invisible.visible = shown && props.showInvisible;
      for (const m of d.materials) m.wireframe = props.wireframe;
    }
    if (skeletonRef.current) skeletonRef.current.visible = props.showSkeleton;
    if (markersRef.current) markersRef.current.visible = props.showMarkers;
  }, [props.wireframe, props.showSkeleton, props.showMarkers, props.showInvisible, props.hiddenParts, props.geometry]);

  return <div ref={mountRef} className="min-h-0 flex-1" />;
}

const IDENTITY = new THREE.Matrix4();
const ONE = new THREE.Vector3(1, 1, 1);

function quat(q: [number, number, number, number]): THREE.Quaternion {
  return new THREE.Quaternion(q[0], q[1], q[2], q[3]).normalize();
}

/** Rest-pose world matrix per node. Parents precede children in Halo node
 *  arrays, so one forward pass composes the chain. */
function nodeWorlds(nodes: ModelGeometry["nodes"]): THREE.Matrix4[] {
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

function hueOf(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return (h % 360) / 360;
}

function disposeChildren(group: THREE.Group) {
  for (const child of [...group.children]) {
    child.traverse((o) => {
      if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments || o instanceof THREE.Points) {
        o.geometry.dispose();
        const m = o.material;
        for (const mat of Array.isArray(m) ? m : [m]) mat.dispose();
      }
    });
    group.remove(child);
  }
}
