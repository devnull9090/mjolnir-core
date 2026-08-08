import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import {
  api,
  type ModelGeometry,
  type ScenarioWorldView,
} from "../lib/api";
import { buildModelGroup, hueOf, parseSbspWorld } from "../lib/three-model";
import { useEditor } from "../stores/editor-store";

/**
 * The World view of a scenario: the level's collision world with every
 * placement drawn on it, selectable and movable — the beginnings of a Sapien.
 *
 * Placements are edited through the same field-patch pipeline as the form
 * view: moving a vehicle writes `vehicles[3].object data.position`, which the
 * open mod project records like any other edit.
 */
export function ScenarioViewer() {
  const index = useEditor((s) => s.selectedTag);
  const [view, setView] = useState<ScenarioWorldView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [worlds, setWorlds] = useState<ArrayBuffer[]>([]);

  useEffect(() => {
    if (index === null) return;
    let stale = false;
    setView(null);
    setWorlds([]);
    setError(null);
    setProgress("reading scenario…");
    (async () => {
      try {
        const v = await api.readScenarioLayout(index);
        if (stale) return;
        setView(v);
        const buffers: ArrayBuffer[] = [];
        const bsps = v.bsp_indices.filter((b): b is number => b !== null);
        for (let i = 0; i < bsps.length; i++) {
          setProgress(`reading structure bsp ${i + 1} of ${bsps.length}…`);
          buffers.push(await api.readSbspWorld(bsps[i]));
          if (stale) return;
        }
        setWorlds(buffers);
        setProgress(null);
      } catch (e) {
        if (!stale) {
          setError(String(e));
          setProgress(null);
        }
      }
    })();
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
  if (progress || !view) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-dim">
        {progress ?? "…"}
      </div>
    );
  }
  return <World key={index} view={view} worlds={worlds} scenarioIndex={index!} />;
}

type Selected = {
  category: number;
  element: number;
  /** The placement's group in the scene. */
  object: THREE.Group;
};

/** Category display colours, keyed by block name; anything else is hashed. */
const CATEGORY_HUES: Record<string, number> = {
  vehicles: 0.32,
  bipeds: 0.02,
  weapons: 0.12,
  equipment: 0.55,
  machines: 0.68,
  controls: 0.78,
  crates: 0.08,
  scenery: 0.45,
  "effect scenery": 0.88,
};

function categoryColor(block: string): THREE.Color {
  const hue = CATEGORY_HUES[block] ?? hueOf(block);
  return new THREE.Color().setHSL(hue, 0.55, 0.6);
}

/** Halo euler (yaw, pitch, roll — radians, applied Z then Y then X in tag
 *  space) as a quaternion. */
function haloEuler(r: [number, number, number]): THREE.Quaternion {
  return new THREE.Quaternion().setFromEuler(new THREE.Euler(r[2], r[1], r[0], "ZYX"));
}

function World(props: {
  view: ScenarioWorldView;
  worlds: ArrayBuffer[];
  scenarioIndex: number;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [selected, setSelected] = useState<{ category: number; element: number } | null>(null);
  const [mode, setMode] = useState<"translate" | "rotate">("translate");
  const [hidden, setHidden] = useState<Set<string>>(new Set(["trigger volumes"]));
  const [saving, setSaving] = useState<string | null>(null);
  const selectedRef = useRef<Selected | null>(null);
  const categoryGroups = useRef<Map<string, THREE.Group>>(new Map());
  const invisibleMatRef = useRef<THREE.MeshStandardMaterial | null>(null);
  const sceneRef = useRef<{
    placements: THREE.Group;
    gizmo: TransformControls;
    highlight: THREE.BoxHelper;
  } | null>(null);

  const layout = props.view.layout;

  // Everything three.js lives in one effect keyed by the loaded data; the
  // cheap toggles poke into it through refs.
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xbfc8d6, 0x2c3036, 1.5));
    const sun = new THREE.DirectionalLight(0xffffff, 1.2);
    sun.position.set(400, 900, 300);
    scene.add(sun);

    const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 20000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    // Tag space is Z-up; one rotation on the root maps it to three's Y-up.
    const model = new THREE.Group();
    model.rotation.x = -Math.PI / 2;
    scene.add(model);

    // --- the world ---------------------------------------------------------
    // One muted tint per collision material: no textures ship in the tag
    // data, but material boundaries (rock/dirt/metal) still read clearly.
    const materialTints = new Map<number, THREE.MeshStandardMaterial>();
    const tintFor = (id: number) => {
      let mat = materialTints.get(id);
      if (!mat) {
        const hue = (id * 0.618034) % 1;
        mat = new THREE.MeshStandardMaterial({
          color: new THREE.Color().setHSL(hue, 0.14, 0.5 + ((id * 0.37) % 0.2)),
          flatShading: true,
          side: THREE.DoubleSide,
          metalness: 0.05,
          roughness: 0.9,
        });
        materialTints.set(id, mat);
      }
      return mat;
    };
    const invisibleMat = new THREE.MeshStandardMaterial({
      color: 0xd06040,
      transparent: true,
      opacity: 0.25,
      side: THREE.DoubleSide,
      depthWrite: false,
      visible: false,
    });
    const worldGroup = new THREE.Group();
    for (const buffer of props.worlds) {
      const parsed = parseSbspWorld(buffer);
      const byDef: THREE.Matrix4[][] = parsed.defs.map(() => []);
      for (const inst of parsed.instances) {
        byDef[inst.def]?.push(inst.matrix);
      }
      const materialsOf = (mesh: NonNullable<typeof parsed.world>) =>
        mesh.groups.map((g) => (g === "invisible" ? invisibleMat : tintFor(g)));
      parsed.defs.forEach((def, d) => {
        if (!def || byDef[d].length === 0) return;
        const mesh = new THREE.InstancedMesh(def.geometry, materialsOf(def), byDef[d].length);
        byDef[d].forEach((m, i) => mesh.setMatrixAt(i, m));
        mesh.instanceMatrix.needsUpdate = true;
        worldGroup.add(mesh);
      });
      if (parsed.world) {
        worldGroup.add(new THREE.Mesh(parsed.world.geometry, materialsOf(parsed.world)));
      }
    }
    model.add(worldGroup);

    // --- placements --------------------------------------------------------
    const placements = new THREE.Group();
    model.add(placements);
    categoryGroups.current = new Map();

    const fallback = new THREE.BoxGeometry(0.3, 0.3, 0.3);
    const modelCache = new Map<number, Promise<ModelGeometry | null>>();
    const proxyCache = new Map<string, THREE.Group>();
    let alive = true;

    layout.categories.forEach((cat, ci) => {
      const group = new THREE.Group();
      group.name = cat.block;
      categoryGroups.current.set(cat.block, group);
      placements.add(group);
      const material = new THREE.MeshStandardMaterial({
        color: categoryColor(cat.block),
        flatShading: true,
        side: THREE.DoubleSide,
        metalness: 0.1,
        roughness: 0.8,
      });

      for (const p of cat.placements) {
        const holder = new THREE.Group();
        holder.position.set(...p.position);
        holder.quaternion.copy(haloEuler(p.rotation));
        if (p.scale > 0 && p.scale !== 1) holder.scale.setScalar(p.scale);
        holder.userData.placement = { category: ci, element: p.element };
        group.add(holder);

        const hlmt = props.view.palette_models[ci]?.[p.palette] ?? null;
        if (hlmt === null) {
          holder.add(new THREE.Mesh(fallback, material));
          continue;
        }
        const key = `${hlmt}`;
        const cached = proxyCache.get(key);
        if (cached) {
          holder.add(cached.clone());
          continue;
        }
        if (!modelCache.has(hlmt)) {
          modelCache.set(
            hlmt,
            api.readModelGeometry(hlmt).catch(() => null),
          );
        }
        void modelCache.get(hlmt)!.then((geo) => {
          if (!alive) return;
          if (!geo || geo.meshes.length === 0) {
            holder.add(new THREE.Mesh(fallback, material));
            return;
          }
          let template = proxyCache.get(key);
          if (!template) {
            template = buildModelGroup(geo, material);
            proxyCache.set(key, template);
          }
          holder.add(template.clone());
        });
      }
    });

    // --- overlays ----------------------------------------------------------
    const overlays: [string, THREE.Group][] = [];

    const triggers = new THREE.Group();
    const triggerMat = new THREE.MeshBasicMaterial({
      color: 0xd8b64a,
      transparent: true,
      opacity: 0.15,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    for (const t of layout.trigger_volumes) {
      const geo = new THREE.BoxGeometry(t.extents[0], t.extents[1], t.extents[2]);
      geo.translate(t.extents[0] / 2, t.extents[1] / 2, t.extents[2] / 2);
      const mesh = new THREE.Mesh(geo, triggerMat);
      const forward = new THREE.Vector3(...t.forward);
      const up = new THREE.Vector3(...t.up);
      const left = new THREE.Vector3().crossVectors(up, forward);
      mesh.matrixAutoUpdate = false;
      mesh.matrix.makeBasis(forward, left, up).setPosition(new THREE.Vector3(...t.position));
      triggers.add(mesh);
    }
    overlays.push(["trigger volumes", triggers]);

    const spawns = new THREE.Group();
    const spawnGeo = new THREE.ConeGeometry(0.12, 0.4, 6);
    // Cones point +Y; rotate to tag-space +Z so they stand up.
    spawnGeo.rotateX(Math.PI / 2);
    const spawnCount = layout.squads.reduce((n, s) => n + s.spawn_points.length, 0);
    if (spawnCount > 0) {
      const mesh = new THREE.InstancedMesh(
        spawnGeo,
        new THREE.MeshStandardMaterial({ flatShading: true }),
        spawnCount,
      );
      let at = 0;
      const m = new THREE.Matrix4();
      for (const squad of layout.squads) {
        const color = new THREE.Color().setHSL(hueOf(squad.name), 0.6, 0.55);
        for (const p of squad.spawn_points) {
          m.makeRotationZ(p.facing[0]).setPosition(
            p.position[0],
            p.position[1],
            p.position[2] + 0.2,
          );
          mesh.setMatrixAt(at, m);
          mesh.setColorAt(at, color);
          at++;
        }
      }
      mesh.instanceMatrix.needsUpdate = true;
      spawns.add(mesh);
    }
    overlays.push(["spawn points", spawns]);

    const starts = new THREE.Group();
    if (layout.player_starts.length > 0) {
      const geo = new THREE.CapsuleGeometry(0.15, 0.4, 3, 8);
      geo.rotateX(Math.PI / 2);
      const mesh = new THREE.InstancedMesh(
        geo,
        new THREE.MeshStandardMaterial({ color: 0x58c470, flatShading: true }),
        layout.player_starts.length,
      );
      const m = new THREE.Matrix4();
      layout.player_starts.forEach((p, i) => {
        m.makeRotationZ(p.facing[0]).setPosition(p.position[0], p.position[1], p.position[2] + 0.35);
        mesh.setMatrixAt(i, m);
      });
      mesh.instanceMatrix.needsUpdate = true;
      starts.add(mesh);
    }
    overlays.push(["player starts", starts]);

    for (const [, g] of overlays) model.add(g);
    for (const [name, g] of overlays) categoryGroups.current.set(name, g);
    invisibleMatRef.current = invisibleMat;

    // --- selection + gizmo -------------------------------------------------
    const highlight = new THREE.BoxHelper(new THREE.Object3D(), 0xf0d060);
    highlight.visible = false;
    scene.add(highlight);

    const gizmo = new TransformControls(camera, renderer.domElement);
    gizmo.addEventListener("dragging-changed", (e) => {
      controls.enabled = !(e as unknown as { value: boolean }).value;
      if (!(e as unknown as { value: boolean }).value) commitTransform();
    });
    scene.add(gizmo.getHelper());

    sceneRef.current = { placements, gizmo, highlight };

    const raycaster = new THREE.Raycaster();
    let downAt: [number, number] | null = null;
    const onDown = (e: PointerEvent) => {
      downAt = [e.clientX, e.clientY];
    };
    const onUp = (e: PointerEvent) => {
      if (!downAt) return;
      const moved = Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]);
      downAt = null;
      if (moved > 5 || gizmo.dragging) return;
      const rect = renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObjects(placements.children, true);
      for (const hit of hits) {
        let o: THREE.Object3D | null = hit.object;
        while (o && !o.userData.placement) o = o.parent;
        if (o?.userData.placement && o.visible) {
          select(o.userData.placement.category, o.userData.placement.element, o as THREE.Group);
          return;
        }
      }
      select(null);
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    // Double-click retargets the orbit pivot — the only sane way to walk a
    // level a kilometre wide.
    const onDouble = (e: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(ndc, camera);
      const hit = raycaster.intersectObjects([worldGroup, placements], true)[0];
      if (hit) controls.target.copy(hit.point);
    };
    renderer.domElement.addEventListener("dblclick", onDouble);

    function select(category: number | null, element?: number, object?: THREE.Group) {
      if (category === null || element === undefined || !object) {
        selectedRef.current = null;
        gizmo.detach();
        highlight.visible = false;
        setSelected(null);
        return;
      }
      selectedRef.current = { category, element, object };
      gizmo.attach(object);
      highlight.setFromObject(object);
      highlight.visible = true;
      setSelected({ category, element });
    }

    function commitTransform() {
      const sel = selectedRef.current;
      if (!sel) return;
      const p = sel.object.position;
      const posPath = `${layout.categories[sel.category].block}[${sel.element}].object data.position`;
      const posValue = `(${fmt(p.x)}, ${fmt(p.y)}, ${fmt(p.z)})`;
      const euler = new THREE.Euler().setFromQuaternion(sel.object.quaternion, "ZYX");
      const rotPath = `${layout.categories[sel.category].block}[${sel.element}].object data.rotation`;
      const rotValue = `(${fmt(euler.z)}, ${fmt(euler.y)}, ${fmt(euler.x)})`;
      highlight.setFromObject(sel.object);
      void writeBack(posPath, posValue, rotPath, rotValue);
    }

    async function writeBack(
      posPath: string,
      posValue: string,
      rotPath: string,
      rotValue: string,
    ) {
      setSaving("saving…");
      try {
        await api.setField(props.scenarioIndex, posPath, posValue);
        await api.setField(props.scenarioIndex, rotPath, rotValue);
        useEditor.setState((s) => ({
          dirtyTags: { ...s.dirtyTags, [props.scenarioIndex]: true },
        }));
        const store = useEditor.getState();
        if (store.project) void store.refreshProject();
        setSaving(null);
      } catch (e) {
        setSaving(String(e));
      }
    }

    // Frame the whole world.
    const bounds = new THREE.Box3().setFromObject(worldGroup);
    if (!bounds.isEmpty()) {
      const center = bounds.getCenter(new THREE.Vector3());
      const size = bounds.getSize(new THREE.Vector3()).length() || 10;
      camera.position.copy(center).add(new THREE.Vector3(0.4, 0.5, 0.4).multiplyScalar(size));
      controls.target.copy(center);
      controls.update();
    }

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
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      renderer.domElement.removeEventListener("dblclick", onDouble);
      gizmo.dispose();
      controls.dispose();
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh || o instanceof THREE.InstancedMesh) {
          o.geometry.dispose();
        }
      });
      renderer.dispose();
      mount.removeChild(renderer.domElement);
      sceneRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.view, props.worlds]);

  // Gizmo mode + visibility toggles.
  useEffect(() => {
    sceneRef.current?.gizmo.setMode(mode);
  }, [mode]);
  useEffect(() => {
    for (const [name, group] of categoryGroups.current) {
      group.visible = !hidden.has(name);
    }
    if (invisibleMatRef.current) {
      invisibleMatRef.current.visible = !hidden.has("invisible surfaces");
    }
  }, [hidden]);

  const selectedInfo = useMemo(() => {
    if (!selected) return null;
    const cat = layout.categories[selected.category];
    const p = cat?.placements.find((x) => x.element === selected.element);
    if (!cat || !p) return null;
    const palette = p.palette >= 0 ? cat.palette[p.palette] : null;
    const name = p.name >= 0 ? layout.object_names[p.name] : null;
    return { cat, p, palette, name };
  }, [selected, layout]);

  function toggle(name: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  const toggles = [
    ...layout.categories.map((c) => [c.block, `${c.block} · ${c.placements.length}`] as const),
    ["trigger volumes", `trigger volumes · ${layout.trigger_volumes.length}`] as const,
    [
      "spawn points",
      `spawn points · ${layout.squads.reduce((n, s) => n + s.spawn_points.length, 0)}`,
    ] as const,
    ["player starts", `player starts · ${layout.player_starts.length}`] as const,
    ["invisible surfaces", "invisible surfaces"] as const,
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border-subtle px-4 py-1.5">
        <button
          type="button"
          onClick={() => setMode("translate")}
          aria-pressed={mode === "translate"}
          className={`border px-1.5 py-0.5 font-mono text-[10px] ${
            mode === "translate"
              ? "border-mjolnir-gold/60 bg-mjolnir-gold/10 text-mjolnir-gold"
              : "border-border-subtle text-text-dim hover:bg-surface-hover"
          }`}
        >
          move
        </button>
        <button
          type="button"
          onClick={() => setMode("rotate")}
          aria-pressed={mode === "rotate"}
          className={`border px-1.5 py-0.5 font-mono text-[10px] ${
            mode === "rotate"
              ? "border-mjolnir-gold/60 bg-mjolnir-gold/10 text-mjolnir-gold"
              : "border-border-subtle text-text-dim hover:bg-surface-hover"
          }`}
        >
          rotate
        </button>
        <span className="mx-1 h-4 w-px bg-border-subtle" />
        {toggles.map(([name, label]) => (
          <button
            key={name}
            type="button"
            onClick={() => toggle(name)}
            aria-pressed={!hidden.has(name)}
            className={`border px-1.5 py-0.5 font-mono text-[10px] ${
              !hidden.has(name)
                ? "border-mjolnir-gold/60 bg-mjolnir-gold/10 text-mjolnir-gold"
                : "border-border-subtle text-text-dim hover:bg-surface-hover"
            }`}
          >
            {label}
          </button>
        ))}
        {saving && (
          <span className="ml-auto font-mono text-[10px] text-text-dim">{saving}</span>
        )}
      </div>
      <div className="relative min-h-0 flex-1">
        <div ref={mountRef} className="absolute inset-0" />
        {selectedInfo && (
          <div className="absolute right-2 top-2 w-64 border border-border-subtle bg-surface-primary/90 p-2 font-mono text-[10px]">
            <p className="text-mjolnir-gold">
              {selectedInfo.cat.block}[{selectedInfo.p.element}]
            </p>
            {selectedInfo.name && <p className="text-text-secondary">name: {selectedInfo.name}</p>}
            {selectedInfo.palette && (
              <p className="truncate text-text-secondary" title={selectedInfo.palette}>
                {selectedInfo.palette}
              </p>
            )}
            <p className="mt-1 text-text-dim">
              drag the gizmo to move; edits are recorded like any field edit
            </p>
          </div>
        )}
        <p className="absolute bottom-2 left-2 font-mono text-[10px] text-text-dim">
          click: select · double-click: focus camera · drag gizmo: edit
        </p>
      </div>
    </div>
  );
}

function fmt(v: number): string {
  return Number.isFinite(v) ? v.toFixed(6) : "0";
}
