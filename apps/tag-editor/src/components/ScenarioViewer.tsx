import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import {
  api,
  type ModelGeometry,
  type ScenarioCellChoice,
  type ScenarioSpawnPoint,
  type ScenarioSquad,
  type ScenarioSquadCell,
  type ScenarioWorldView,
} from "../lib/api";
import { buildModelGroup, hueOf, parseSbspWorld } from "../lib/three-model";
import {
  loadRenderGroup,
  type MeshCache,
  type TextureCache,
} from "../lib/render-mesh";
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

/** What the gizmo is on: a placed object, or one squad spawn point. Spawn
 *  `squad` and `point` are positions in the view's own squad list; their
 *  `element` fields give the tag paths. */
type Pick =
  | { kind: "placement"; category: number; element: number }
  | { kind: "spawn"; squad: number; point: number };

type Selected = Pick & {
  /** The placement's group, or the stand-in a spawn point is dragged by. */
  object: THREE.Group;
};

/** How far a duplicated spawn point steps sideways, in world units. */
const DUP_STEP = 0.3;
/** The squad definition's limit on spawn points. */
const SPAWN_POINTS_MAX = 128;

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
  const [selected, setSelected] = useState<Pick | null>(null);
  // Bumped when the view's own squad copy changes, so the panel re-reads it.
  const [squadsVersion, setSquadsVersion] = useState(0);
  const [mode, setMode] = useState<"translate" | "rotate">("translate");
  const [hidden, setHidden] = useState<Set<string>>(new Set(["trigger volumes"]));
  const [saving, setSaving] = useState<string | null>(null);
  const exportLevel = useEditor((s) => s.exportLevel);
  const [exporting, setExporting] = useState<string | null>(null);
  async function onExportLevel() {
    const dest = await openDialog({ directory: true, title: "Folder for the level's .glb files" });
    if (!dest || Array.isArray(dest)) return;
    setExporting("exporting level geometry…");
    const summary = await exportLevel(dest, false, false);
    if (!summary) {
      setExporting(null);
      return;
    }
    const mb = (summary.bytes / 1_048_576).toFixed(0);
    setExporting(
      `wrote ${summary.files} of ${summary.cells} cells, ${summary.placements.toLocaleString()} placements, ${mb} MB`,
    );
  }
  const selectedRef = useRef<Selected | null>(null);
  const categoryGroups = useRef<Map<string, THREE.Group>>(new Map());
  const invisibleMatRef = useRef<THREE.MeshStandardMaterial | null>(null);
  const sceneRef = useRef<{
    placements: THREE.Group;
    gizmo: TransformControls;
    highlight: THREE.BoxHelper;
    duplicateSpawn: () => Promise<void>;
    setCellCount: (squad: number, cell: number, count: number) => Promise<void>;
  } | null>(null);

  const layout = props.view.layout;
  // The squads as this view has edited them: spawn points move, duplicate
  // and renumber here without reading the whole scenario back.
  const [firstSquads] = useState(() => structuredClone(layout.squads));
  const squadsRef = useRef<ScenarioSquad[]>(firstSquads);

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
    // Render models: mesh geometry and texture caches span the whole level,
    // template groups are keyed by the set of meshes an object binds.
    const meshCache: MeshCache = new Map();
    const textureCache: TextureCache = new Map();
    const renderCache = new Map<string, Promise<THREE.Group | null>>();
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

      // The collision shell (or a box), for objects with no reachable or no
      // readable render mesh.
      const attachProxy = (holder: THREE.Group, hlmt: number | null) => {
        if (hlmt === null) {
          holder.add(new THREE.Mesh(fallback, material));
          return;
        }
        const key = `${hlmt}`;
        const cached = proxyCache.get(key);
        if (cached) {
          holder.add(cached.clone());
          return;
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
      };

      for (const p of cat.placements) {
        const holder = new THREE.Group();
        holder.position.set(...p.position);
        holder.quaternion.copy(haloEuler(p.rotation));
        if (p.scale > 0 && p.scale !== 1) holder.scale.setScalar(p.scale);
        holder.userData.placement = { category: ci, element: p.element };
        group.add(holder);

        const hlmt = props.view.palette_models[ci]?.[p.palette] ?? null;
        const refs = props.view.palette_render[ci]?.[p.palette] ?? [];
        if (refs.length === 0) {
          attachProxy(holder, hlmt);
          continue;
        }
        // The real textured mesh; instances of one object share a template
        // (clones share geometries and materials).
        const key = refs.map((r) => r.mesh).join(",");
        if (!renderCache.has(key)) {
          renderCache.set(
            key,
            loadRenderGroup(refs, meshCache, textureCache, () => alive),
          );
        }
        void renderCache.get(key)!.then((template) => {
          if (!alive) return;
          if (!template) {
            // Skeletal-Nanite placeholders and unreadable meshes land here.
            attachProxy(holder, hlmt);
            return;
          }
          holder.add(template.children.length > 0 ? template.clone() : template);
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

    // Spawn points: one instanced cone each, coloured by squad, built from
    // the view's own squad copy so a duplicate can rebuild it in place.
    squadsRef.current = structuredClone(layout.squads);
    const spawns = new THREE.Group();
    const spawnGeo = new THREE.ConeGeometry(0.12, 0.4, 6);
    // Cones point +Y; rotate to tag-space +Z so they stand up.
    spawnGeo.rotateX(Math.PI / 2);
    const spawnMat = new THREE.MeshStandardMaterial({ flatShading: true });
    let spawnMesh: THREE.InstancedMesh | null = null;
    // Instance id -> which squad and point it draws.
    let spawnAt: { squad: number; point: number }[] = [];
    const spawnMatrix = (position: number[], yaw: number) =>
      new THREE.Matrix4()
        .makeRotationZ(yaw)
        .setPosition(position[0], position[1], position[2] + 0.2);
    const buildSpawns = () => {
      if (spawnMesh) {
        spawns.remove(spawnMesh);
        spawnMesh.dispose();
        spawnMesh = null;
      }
      spawnAt = [];
      squadsRef.current.forEach((squad, s) =>
        squad.spawn_points.forEach((_, p) => spawnAt.push({ squad: s, point: p })),
      );
      if (spawnAt.length === 0) return;
      const mesh = new THREE.InstancedMesh(spawnGeo, spawnMat, spawnAt.length);
      spawnAt.forEach(({ squad, point }, i) => {
        const sq = squadsRef.current[squad];
        const p = sq.spawn_points[point];
        mesh.setMatrixAt(i, spawnMatrix(p.position, p.facing[0]));
        mesh.setColorAt(i, new THREE.Color().setHSL(hueOf(sq.name), 0.6, 0.55));
      });
      mesh.instanceMatrix.needsUpdate = true;
      spawns.add(mesh);
      spawnMesh = mesh;
    };
    buildSpawns();
    overlays.push(["spawn points", spawns]);

    // The ring a selected spawn point wears, inside its drag stand-in.
    const ringGeo = new THREE.TorusGeometry(0.28, 0.03, 6, 24);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0xf0d060 });

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
    // A spawn point's cone follows its stand-in while it is dragged.
    gizmo.addEventListener("objectChange", () => {
      const sel = selectedRef.current;
      if (sel?.kind !== "spawn" || !spawnMesh) return;
      const i = spawnAt.findIndex((a) => a.squad === sel.squad && a.point === sel.point);
      if (i < 0) return;
      const o = sel.object;
      spawnMesh.setMatrixAt(i, spawnMatrix([o.position.x, o.position.y, o.position.z], yawOf(o)));
      spawnMesh.instanceMatrix.needsUpdate = true;
    });
    scene.add(gizmo.getHelper());

    // The stand-in a selected spawn point is dragged by, in tag space.
    const spawnHandle = new THREE.Group();
    spawnHandle.add(new THREE.Mesh(ringGeo, ringMat));
    spawnHandle.visible = false;
    model.add(spawnHandle);

    sceneRef.current = { placements, gizmo, highlight, duplicateSpawn, setCellCount };

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
      // The nearest of a placement and a spawn point wins.
      let placementHit: { distance: number; object: THREE.Group } | null = null;
      for (const hit of raycaster.intersectObjects(placements.children, true)) {
        let o: THREE.Object3D | null = hit.object;
        while (o && !o.userData.placement) o = o.parent;
        if (o?.userData.placement && o.visible && o.parent?.visible) {
          placementHit = { distance: hit.distance, object: o as THREE.Group };
          break;
        }
      }
      const spawnHit =
        spawnMesh && spawns.visible
          ? raycaster.intersectObject(spawnMesh, false).find((h) => h.instanceId !== undefined)
          : undefined;
      if (spawnHit && (!placementHit || spawnHit.distance < placementHit.distance)) {
        const at = spawnAt[spawnHit.instanceId!];
        selectSpawn(at.squad, at.point);
        return;
      }
      if (placementHit) {
        const p = placementHit.object.userData.placement;
        select(p.category, p.element, placementHit.object);
        return;
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

    function clearSelection() {
      selectedRef.current = null;
      gizmo.detach();
      highlight.visible = false;
      spawnHandle.visible = false;
      setSelected(null);
    }

    function select(category: number | null, element?: number, object?: THREE.Group) {
      if (category === null || element === undefined || !object) {
        clearSelection();
        return;
      }
      spawnHandle.visible = false;
      selectedRef.current = { kind: "placement", category, element, object };
      gizmo.showX = gizmo.showY = gizmo.showZ = true;
      gizmo.attach(object);
      highlight.setFromObject(object);
      highlight.visible = true;
      setSelected({ kind: "placement", category, element });
    }

    /** A spawn point only turns about the up axis (three's Y, tag Z). */
    function applySpawnAxes() {
      const rotating = gizmo.getMode() === "rotate";
      gizmo.showX = gizmo.showZ = !rotating;
      gizmo.showY = true;
    }

    /** Put the gizmo on one spawn point, by its squad and point position. */
    function selectSpawn(squad: number, point: number) {
      const p = squadsRef.current[squad]?.spawn_points[point];
      if (!p) {
        clearSelection();
        return;
      }
      spawnHandle.position.set(p.position[0], p.position[1], p.position[2]);
      spawnHandle.quaternion.setFromAxisAngle(new THREE.Vector3(0, 0, 1), p.facing[0]);
      spawnHandle.visible = true;
      highlight.visible = false;
      selectedRef.current = { kind: "spawn", squad, point, object: spawnHandle };
      gizmo.attach(spawnHandle);
      applySpawnAxes();
      setSelected({ kind: "spawn", squad, point });
    }

    function commitTransform() {
      const sel = selectedRef.current;
      if (!sel) return;
      const o = sel.object;
      if (sel.kind === "spawn") {
        const sq = squadsRef.current[sel.squad];
        const p = sq.spawn_points[sel.point];
        p.position = [o.position.x, o.position.y, o.position.z];
        p.facing = [yawOf(o), p.facing[1]];
        const base = `squads[${sq.element}].spawn points[${p.element}]`;
        void writeBack([
          [`${base}.position`, vec(p.position)],
          [`${base}.facing (yaw, pitch)`, `(${fmt(p.facing[0])}, ${fmt(p.facing[1])})`],
        ]);
        return;
      }
      const p = o.position;
      const block = `${layout.categories[sel.category].block}[${sel.element}]`;
      const euler = new THREE.Euler().setFromQuaternion(o.quaternion, "ZYX");
      highlight.setFromObject(o);
      void writeBack([
        [`${block}.object data.position`, `(${fmt(p.x)}, ${fmt(p.y)}, ${fmt(p.z)})`],
        [`${block}.object data.rotation`, `(${fmt(euler.z)}, ${fmt(euler.y)}, ${fmt(euler.x)})`],
      ]);
    }

    /** Record field edits through the same pipeline as the form view. */
    async function writeBack(edits: [string, string][]): Promise<boolean> {
      setSaving("saving…");
      try {
        for (const [path, value] of edits) {
          await api.setField(props.scenarioIndex, path, value);
        }
        afterEdit();
        setSaving(null);
        return true;
      } catch (e) {
        setSaving(String(e));
        return false;
      }
    }

    function afterEdit() {
      useEditor.setState((s) => ({
        dirtyTags: { ...s.dirtyTags, [props.scenarioIndex]: true },
      }));
      const store = useEditor.getState();
      if (store.project) void store.refreshProject();
    }

    /**
     * Copy the selected spawn point into the same squad and cell, a step to
     * its side, and select the copy. The copy's name is cleared so a script
     * naming the original still finds exactly one point.
     */
    async function duplicateSpawn() {
      const sel = selectedRef.current;
      if (sel?.kind !== "spawn") return;
      const sq = squadsRef.current[sel.squad];
      const p = sq.spawn_points[sel.point];
      const list = `squads[${sq.element}].spawn points`;
      const yaw = p.facing[0];
      const position: [number, number, number] = [
        p.position[0] - Math.sin(yaw) * DUP_STEP,
        p.position[1] + Math.cos(yaw) * DUP_STEP,
        p.position[2],
      ];
      setSaving("duplicating…");
      try {
        await api.duplicateElement(props.scenarioIndex, list, p.element);
      } catch (e) {
        setSaving(String(e));
        return;
      }
      // The copy sits directly after the original; everything after it in
      // this squad moves up one.
      for (const q of sq.spawn_points) if (q.element > p.element) q.element += 1;
      const copy = { ...p, element: p.element + 1, name: "", position };
      sq.spawn_points.splice(sel.point + 1, 0, copy);
      buildSpawns();
      selectSpawn(sel.squad, sel.point + 1);
      setSquadsVersion((v) => v + 1);
      afterEdit();
      const ok = await writeBack([
        [`${list}[${copy.element}].position`, vec(position)],
        [`${list}[${copy.element}].name`, ""],
      ]);
      if (ok) void useEditor.getState().refreshTag();
    }

    /** Set how many actors one designer cell of a squad spawns. */
    async function setCellCount(squad: number, cell: number, count: number) {
      const sq = squadsRef.current[squad];
      const c = sq?.cells[cell];
      if (!c || count < 0) return;
      const ok = await writeBack([
        [`squads[${sq.element}].designer.cells[${cell}].normal diff count`, String(count)],
      ]);
      if (!ok) return;
      c.normal_count = count;
      setSquadsVersion((v) => v + 1);
      void useEditor.getState().refreshTag();
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
      spawnGeo.dispose();
      spawnMat.dispose();
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh || o instanceof THREE.InstancedMesh) {
          o.geometry.dispose();
          const m = o.material;
          for (const mat of Array.isArray(m) ? m : [m]) {
            if (mat instanceof THREE.MeshStandardMaterial) mat.map?.dispose();
            mat.dispose();
          }
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
    const gizmo = sceneRef.current?.gizmo;
    if (!gizmo) return;
    gizmo.setMode(mode);
    // A spawn point only turns about the up axis (three's Y, tag Z).
    if (selectedRef.current?.kind === "spawn") {
      gizmo.showX = gizmo.showZ = mode !== "rotate";
      gizmo.showY = true;
    }
  }, [mode]);
  useEffect(() => {
    for (const [name, group] of categoryGroups.current) {
      group.visible = !hidden.has(name);
    }
    if (invisibleMatRef.current) {
      invisibleMatRef.current.visible = !hidden.has("invisible surfaces");
    }
  }, [hidden]);

  const spawnInfo = useMemo(() => {
    if (selected?.kind !== "spawn") return null;
    const squad = squadsRef.current[selected.squad];
    const point = squad?.spawn_points[selected.point];
    if (!squad || !point) return null;
    const cell = point.cell >= 0 ? squad.cells[point.cell] : undefined;
    const cellPoints = squad.spawn_points.filter((p) => p.cell === point.cell).length;
    return { squad, point, cell, cellPoints, full: squad.spawn_points.length >= SPAWN_POINTS_MAX };
    // squadsVersion: the copy is edited in place.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, squadsVersion]);

  const selectedInfo = useMemo(() => {
    if (selected?.kind !== "placement") return null;
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
      `spawn points · ${squadsRef.current.reduce((n, s) => n + s.spawn_points.length, 0)}`,
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
        <span className="mx-1 h-4 w-px bg-border-subtle" />
        <button
          type="button"
          onClick={onExportLevel}
          title="Every placed Unreal static mesh of this mission, one glTF binary per World Partition cell, at its world transform"
          className="border border-border-subtle px-1.5 py-0.5 font-mono text-[10px] text-text-dim hover:bg-surface-hover"
        >
          export level geometry…
        </button>
        {exporting && <span className="font-mono text-[10px] text-text-dim">{exporting}</span>}
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
        {selected?.kind === "spawn" && spawnInfo && (
          <div className="absolute right-2 top-2 w-80 border border-border-subtle bg-surface-primary/90 p-2 font-mono text-[10px]">
            <p className="text-mjolnir-gold">
              squads[{spawnInfo.squad.element}].spawn points[{spawnInfo.point.element}]
            </p>
            <p className="truncate text-text-secondary" title={spawnInfo.squad.name}>
              squad: {spawnInfo.squad.name || <em>unnamed</em>}
            </p>
            {spawnInfo.point.name && (
              <p className="truncate text-text-secondary">point: {spawnInfo.point.name}</p>
            )}
            {spawnInfo.cell ? (
              <div className="mt-1 flex items-center gap-1.5 text-text-secondary">
                <span className="min-w-0 truncate" title={spawnInfo.cell.name}>
                  cell {spawnInfo.cell.name || spawnInfo.point.cell}:
                </span>
                <button
                  type="button"
                  className="border border-border-subtle px-1 hover:bg-surface-hover disabled:opacity-40"
                  disabled={spawnInfo.cell.normal_count <= 0}
                  title="Spawn one fewer actor from this cell"
                  onClick={() =>
                    void sceneRef.current?.setCellCount(
                      selected.squad,
                      spawnInfo.point.cell,
                      spawnInfo.cell!.normal_count - 1,
                    )
                  }
                >
                  −
                </button>
                <span className="text-text-primary">{spawnInfo.cell.normal_count}</span>
                <button
                  type="button"
                  className="border border-border-subtle px-1 hover:bg-surface-hover"
                  title="Spawn one more actor from this cell (normal diff count)"
                  onClick={() =>
                    void sceneRef.current?.setCellCount(
                      selected.squad,
                      spawnInfo.point.cell,
                      spawnInfo.cell!.normal_count + 1,
                    )
                  }
                >
                  +
                </button>
                <span className="text-text-dim">
                  actors · {spawnInfo.cellPoints} point{spawnInfo.cellPoints === 1 ? "" : "s"}
                </span>
              </div>
            ) : (
              <p className="mt-1 text-text-dim">no designer cell</p>
            )}
            {spawnInfo.cell && <CellContents cell={spawnInfo.cell} point={spawnInfo.point} />}
            <div className="mt-1.5 flex items-center gap-2">
              <button
                type="button"
                className="border border-border-subtle px-1.5 py-0.5 text-text-secondary hover:bg-surface-hover hover:text-mjolnir-gold disabled:opacity-40"
                disabled={spawnInfo.full}
                title={
                  spawnInfo.full
                    ? `A squad holds at most ${SPAWN_POINTS_MAX} spawn points`
                    : "Copy this spawn point a step to its side, in the same squad and cell"
                }
                onClick={() => void sceneRef.current?.duplicateSpawn()}
              >
                dup
              </button>
              <span className="text-text-dim">drag to move · rotate turns the facing</span>
            </div>
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

/** The last part of a tag path: `crewman` for `…\ai\crewman`. */
function tagName(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

/**
 * A weighted choice list as one line: `crewman 50% · crewman_female 50%`.
 * A single choice is just its name; null when the list is empty.
 */
function describeChoices(choices: ScenarioCellChoice[]): string | null {
  const named = choices.filter((c) => c.path !== "");
  if (named.length === 0) return null;
  if (named.length === 1) return tagName(named[0].path);
  const total = named.reduce((n, c) => n + Math.max(c.chance, 0), 0);
  return named
    .map((c) =>
      total > 0
        ? `${tagName(c.path)} ${Math.round((Math.max(c.chance, 0) / total) * 100)}%`
        : tagName(c.path),
    )
    .join(" · ");
}

/** What one designer cell spawns, with the selected point's own overrides. */
function CellContents({ cell, point }: { cell: ScenarioSquadCell; point: ScenarioSpawnPoint }) {
  const rows: [string, string | null, string?][] = [
    ["actor", describeChoices(cell.characters), point.character],
    ["weapon", describeChoices(cell.weapons), point.weapon],
    ["secondary", describeChoices(cell.secondary_weapons)],
    ["equipment", describeChoices(cell.equipment)],
    ["vehicle", cell.vehicle ? tagName(cell.vehicle) : null, point.vehicle],
  ];
  return (
    <div className="mt-1 border-l border-border-subtle pl-2 text-text-secondary">
      {rows.map(([label, value, override]) =>
        value || override ? (
          <p key={label} className="truncate" title={value ?? undefined}>
            <span className="text-text-dim">{label}: </span>
            {override ? (
              <>
                {tagName(override)}
                <span className="text-text-dim"> (this point{value ? `; cell: ${value}` : ""})</span>
              </>
            ) : (
              value
            )}
          </p>
        ) : null,
      )}
      {cell.upgrade && cell.upgrade !== "normal" && (
        <p>
          <span className="text-text-dim">upgrade: </span>
          {cell.upgrade}
        </p>
      )}
    </div>
  );
}

function vec(v: [number, number, number]): string {
  return `(${fmt(v[0])}, ${fmt(v[1])}, ${fmt(v[2])})`;
}

/** Yaw of an object turned only about tag-space Z. */
function yawOf(o: THREE.Object3D): number {
  return new THREE.Euler().setFromQuaternion(o.quaternion, "ZYX").z;
}
