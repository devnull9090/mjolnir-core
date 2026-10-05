/**
 * The three.js half of MatchMap, imported only when a match page draws a
 * map. The model is a converted map's preview (tools/level/export_map_preview.py):
 * glTF metres, Y up, vertex colours. A match's Unreal positions (centimetres,
 * Z up) are (x, z, y) / 100 of it.
 *
 * Two views. "top" is the minimap: an orthographic camera looking straight
 * down, CE's X across and its Y up the screen, which is Unreal's Y down, as
 * the editor's top view and the plain plot draw it. "3d" orbits. The map's
 * faces point into the play space, so culling their backs shows the inside
 * of an indoor map from above or outside. A cut plane takes off everything
 * above a height, the floors over a lower one included.
 *
 * A replay sets a time: marks after it are hidden, the ones within `fresh`
 * of it drawn larger and brighter, older ones faded.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import type { DeathMark, KillMark, Point } from "./positions";

export type ViewMode = "top" | "3d";
/** A hovered dot's line, at the pointer; `flip` puts it left of a pointer past the middle. */
export type Hover = { x: number; y: number; flip: boolean; text: string } | null;

const KILLER = new THREE.Color("#d4a843");
const VICTIM = new THREE.Color("#ef4444");
const LINE = new THREE.Color("#c9d1d9");
/** What an old mark fades towards in a replay: the page's surface. */
const FADED = new THREE.Color("#161b22");
/** Dot radius in the top view, CSS pixels. */
const DOT_PX = 5;
/** Dot radius in the 3D view: about a Spartan's half width, metres. */
const DOT_M = 0.45;
/** A cut plane height above any map. */
const NO_CUT = 1e6;

const toWorld = (p: Point) => new THREE.Vector3(p[0] / 100, p[2] / 100, p[1] / 100);

export class MapViewer {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private top = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10000);
  private persp = new THREE.PerspectiveCamera(45, 1, 0.5, 20000);
  private controls: OrbitControls | null = null;
  private mode: ViewMode = "top";
  private bounds = new THREE.Box3();
  private frame = new THREE.Box3();
  private cut = new THREE.Plane(new THREE.Vector3(0, -1, 0), NO_CUT);
  private killers: THREE.InstancedMesh | null = null;
  private victims: THREE.InstancedMesh | null = null;
  private lines: THREE.LineSegments | null = null;
  private killerAt: THREE.Vector3[] = [];
  private victimAt: THREE.Vector3[] = [];
  private killerLabel: string[] = [];
  private victimLabel: string[] = [];
  private killerT: number[] = [];
  private victimT: number[] = [];
  /** Each line's time; the lines are in time order. */
  private lineT: number[] = [];
  private time: number | null = null;
  private fresh = 10000;
  private dot = new THREE.SphereGeometry(1, 16, 12);
  private frameRequest = 0;
  private resize: ResizeObserver;
  private raycaster = new THREE.Raycaster();
  private hovered: string | null = null;

  private constructor(
    private container: HTMLElement,
    private onHover: (h: Hover) => void,
  ) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.localClippingEnabled = true;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    const canvas = this.renderer.domElement;
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    container.appendChild(canvas);

    this.scene.add(new THREE.AmbientLight(0xffffff, 1.5));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(0.35, 1, 0.25);
    this.scene.add(sun);

    this.top.up.set(0, 0, -1);
    this.resize = new ResizeObserver(() => this.fit());
    this.resize.observe(container);
    canvas.addEventListener("pointermove", this.pointerMove);
    canvas.addEventListener("pointerleave", this.pointerLeave);
  }

  /** Throws when the browser has no WebGL or the model does not load. */
  static async create(container: HTMLElement, url: string, onHover: (h: Hover) => void): Promise<MapViewer> {
    const viewer = new MapViewer(container, onHover);
    try {
      const gltf = await new GLTFLoader().loadAsync(url);
      const material = new THREE.MeshLambertMaterial({ vertexColors: true, clippingPlanes: [viewer.cut] });
      gltf.scene.traverse((o) => {
        if (o instanceof THREE.Mesh) {
          (o.material as THREE.Material).dispose();
          o.material = material;
        }
      });
      viewer.scene.add(gltf.scene);
      viewer.bounds.setFromObject(gltf.scene);
      return viewer;
    } catch (e) {
      viewer.dispose();
      throw e;
    }
  }

  /** The height range a cut can take, metres. */
  get heights(): [number, number] {
    return [this.bounds.min.y, this.bounds.max.y];
  }

  setMarks(kills: KillMark[], deaths: DeathMark[]) {
    for (const o of [this.killers, this.victims, this.lines]) {
      if (!o) continue;
      this.scene.remove(o);
      (o.material as THREE.Material).dispose();
      if (o instanceof THREE.LineSegments) o.geometry.dispose();
      else o.dispose();
    }
    const withKiller = kills.filter((k) => k.from).sort((a, b) => a.t_ms - b.t_ms);
    this.killerAt = withKiller.map((k) => toWorld(k.from!));
    this.killerLabel = withKiller.map((k) => k.label);
    this.killerT = withKiller.map((k) => k.t_ms);
    this.lineT = this.killerT;
    this.victimAt = [...kills.map((k) => toWorld(k.to)), ...deaths.map((d) => toWorld(d.at))];
    this.victimLabel = [...kills.map((k) => k.label), ...deaths.map((d) => d.label)];
    this.victimT = [...kills.map((k) => k.t_ms), ...deaths.map((d) => d.t_ms)];

    const dots = (color: THREE.Color, count: number) => {
      const mesh = new THREE.InstancedMesh(
        this.dot,
        new THREE.MeshBasicMaterial({ clippingPlanes: [this.cut] }),
        Math.max(count, 1),
      );
      mesh.count = count;
      // Per-instance colour, so a replay can fade the old ones.
      for (let i = 0; i < count; i++) mesh.setColorAt(i, color);
      mesh.userData.colour = color;
      mesh.renderOrder = 2;
      mesh.frustumCulled = false;
      this.scene.add(mesh);
      return mesh;
    };
    this.killers = dots(KILLER, this.killerAt.length);
    this.victims = dots(VICTIM, this.victimAt.length);

    const segments = withKiller.flatMap((k) => [toWorld(k.from!), toWorld(k.to)]);
    const lineGeometry = new THREE.BufferGeometry().setFromPoints(segments);
    lineGeometry.setAttribute("color", new THREE.Float32BufferAttribute(new Float32Array(segments.length * 3), 3));
    this.lines = new THREE.LineSegments(
      lineGeometry,
      new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.55, clippingPlanes: [this.cut] }),
    );
    this.lines.renderOrder = 1;
    this.lines.frustumCulled = false;
    this.scene.add(this.lines);

    // Frame the action, with room around it, or the whole map without any.
    const all = [...this.killerAt, ...this.victimAt];
    if (all.length) {
      this.frame.setFromPoints(all);
      const size = this.bounds.getSize(new THREE.Vector3());
      this.frame.expandByScalar(Math.max(size.x, size.z) * 0.08);
      this.frame.intersect(this.bounds.clone().expandByScalar(1));
      if (this.frame.isEmpty()) this.frame.copy(this.bounds);
    } else {
      this.frame.copy(this.bounds);
    }
    this.applyDepthTest();
    this.reset();
  }

  setMode(mode: ViewMode) {
    this.mode = mode;
    this.applyDepthTest();
    this.reset();
  }

  /** Show the match as it stood at `time` ms (null: all of it). Marks
   * within `fresh` ms before it are drawn as just happened. */
  setTime(time: number | null, fresh = 10000) {
    this.time = time;
    this.fresh = Math.max(fresh, 1);
    this.requestRender();
  }

  /** Cut away everything above `t` of the way up the map (1: nothing). */
  setCut(t: number) {
    const [lo, hi] = this.heights;
    this.cut.constant = t >= 1 ? NO_CUT : lo + (hi - lo) * t;
    this.requestRender();
  }

  /** Back to the framing the marks were set with. */
  reset() {
    this.controls?.dispose();
    const camera = this.mode === "top" ? this.top : this.persp;
    const controls = new OrbitControls(camera, this.renderer.domElement);
    const centre = this.frame.getCenter(new THREE.Vector3());
    const size = this.frame.getSize(new THREE.Vector3());
    if (this.mode === "top") {
      // Looking straight down; panning and zooming only.
      this.top.position.set(centre.x, this.bounds.max.y + 50, centre.z);
      this.top.near = 1;
      this.top.far = this.bounds.max.y - this.bounds.min.y + 100;
      this.top.zoom = 1;
      controls.target.set(centre.x, this.bounds.min.y, centre.z);
      controls.enableRotate = false;
      controls.zoomToCursor = true;
      controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
      controls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_PAN };
    } else {
      const radius = Math.max(size.x, size.z, 20) * 0.45;
      const dir = new THREE.Vector3(0.55, 0.75, 0.9).normalize();
      const fov = THREE.MathUtils.degToRad(this.persp.fov);
      this.persp.position.copy(centre).addScaledVector(dir, radius / Math.sin(fov / 2));
      controls.target.copy(centre);
      controls.maxPolarAngle = Math.PI * 0.495;
    }
    controls.addEventListener("change", () => this.requestRender());
    this.controls = controls;
    this.fit();
    controls.update();
  }

  dispose() {
    cancelAnimationFrame(this.frameRequest);
    this.resize.disconnect();
    this.controls?.dispose();
    const canvas = this.renderer.domElement;
    canvas.removeEventListener("pointermove", this.pointerMove);
    canvas.removeEventListener("pointerleave", this.pointerLeave);
    this.scene.traverse((o) => {
      if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments) {
        o.geometry.dispose();
        (o.material as THREE.Material).dispose();
      }
    });
    this.dot.dispose();
    this.renderer.dispose();
    canvas.remove();
  }

  /** Size the cameras to the container, the top view to the frame. */
  private fit() {
    const w = Math.max(this.container.clientWidth, 1);
    const h = Math.max(this.container.clientHeight, 1);
    this.renderer.setSize(w, h, false);
    const aspect = w / h;
    const size = this.frame.getSize(new THREE.Vector3());
    const half = Math.max(size.x / aspect, size.z, 10) / 2;
    this.top.left = -half * aspect;
    this.top.right = half * aspect;
    this.top.top = half;
    this.top.bottom = -half;
    this.top.updateProjectionMatrix();
    this.persp.aspect = aspect;
    this.persp.updateProjectionMatrix();
    this.requestRender();
  }

  /** Markers drawn over the map in the top view, among it in 3D. */
  private applyDepthTest() {
    const over = this.mode === "top";
    for (const o of [this.killers, this.victims, this.lines]) {
      if (!o) continue;
      const m = o.material as THREE.Material;
      m.depthTest = !over;
      m.needsUpdate = true;
    }
  }

  private requestRender() {
    if (this.frameRequest) return;
    this.frameRequest = requestAnimationFrame(() => {
      this.frameRequest = 0;
      this.placeMarks();
      this.renderer.render(this.scene, this.mode === "top" ? this.top : this.persp);
    });
  }

  /** How far a mark at `t` is into the replay: null when it has not
   * happened yet, 1 when it just did, 0 once it is old (or with no replay). */
  private freshness(t: number): number | null {
    if (this.time === null) return 0;
    if (t > this.time) return null;
    return Math.max(0, 1 - (this.time - t) / this.fresh);
  }

  /** A mark's colour: its own, faded when a replay has moved past it. */
  private shade(base: THREE.Color, f: number, out: THREE.Color): THREE.Color {
    out.copy(base);
    if (this.time !== null) out.lerp(FADED, 0.6 * (1 - f));
    return out;
  }

  /** Dots a few pixels across in the top view whatever the zoom; a
   * Spartan's width in 3D, growing far off so a big map's dots stay
   * visible. A replay hides what has not happened and grows what just did. */
  private placeMarks() {
    let radius: number;
    if (this.mode === "top") {
      const perPixel = (this.top.top - this.top.bottom) / this.top.zoom / Math.max(this.container.clientHeight, 1);
      radius = DOT_PX * perPixel;
    } else {
      const distance = this.controls ? this.persp.position.distanceTo(this.controls.target) : 50;
      radius = Math.max(DOT_M, distance * 0.006);
    }
    const m = new THREE.Matrix4();
    const scale = new THREE.Vector3();
    const q = new THREE.Quaternion();
    const c = new THREE.Color();
    for (const [mesh, at, times] of [
      [this.killers, this.killerAt, this.killerT],
      [this.victims, this.victimAt, this.victimT],
    ] as const) {
      if (!mesh) continue;
      at.forEach((p, i) => {
        const f = this.freshness(times[i]);
        scale.setScalar(f === null ? 0 : radius * (1 + 1.2 * f));
        mesh.setMatrixAt(i, m.compose(p, q, scale));
        mesh.setColorAt(i, this.shade(mesh.userData.colour, f ?? 0, c));
      });
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      mesh.computeBoundingSphere();
    }
    if (this.lines) {
      const colours = this.lines.geometry.getAttribute("color") as THREE.BufferAttribute;
      let shown = 0;
      this.lineT.forEach((t, i) => {
        const f = this.freshness(t);
        if (f === null) return;
        shown = i + 1;
        this.shade(LINE, f, c);
        colours.setXYZ(i * 2, c.r, c.g, c.b);
        colours.setXYZ(i * 2 + 1, c.r, c.g, c.b);
      });
      colours.needsUpdate = true;
      this.lines.geometry.setDrawRange(0, shown * 2);
    }
  }

  private pointerMove = (e: PointerEvent) => {
    if (e.buttons) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(ndc, this.mode === "top" ? this.top : this.persp);
    const targets = [this.victims, this.killers].filter((m): m is THREE.InstancedMesh => !!m);
    // A dot cut away is not there to hover.
    const hit = this.raycaster
      .intersectObjects(targets, false)
      .find((h) => this.cut.distanceToPoint(h.point) >= 0 && h.instanceId !== undefined);
    const text = hit ? (hit.object === this.killers ? this.killerLabel : this.victimLabel)[hit.instanceId!] : null;
    this.renderer.domElement.style.cursor = text ? "pointer" : "";
    if (text === this.hovered && !text) return;
    this.hovered = text;
    const x = e.clientX - rect.left;
    this.onHover(text ? { x, y: e.clientY - rect.top, flip: x > rect.width / 2, text } : null);
  };

  private pointerLeave = () => {
    this.hovered = null;
    this.onHover(null);
  };
}
