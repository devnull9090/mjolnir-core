/**
 * In-browser stand-in for the Tauri backend, active only when the app runs
 * outside Tauri (plain `vite dev`). It exists so the interface can be built
 * and reviewed without a game installation; the data is a small hand-written
 * imitation of a scenario tag and is not shipped content.
 */
import type {
  DirEntry,
  EditResult,
  ExportView,
  GroupSummary,
  HubStatus,
  Install,
  LinkPoll,
  LinkStart,
  NodeView,
  ProjectView,
  PublishView,
  SigningStatus,
  TagSummary,
  TagView,
  TestView,
  NewTagView,
} from "./api";

/** A slice of the virtual filesystem, shaped like the real one. */
const mockFiles: Omit<DirEntry, "name" | "children">[] = [
  { path: "meshes/Env/Sample/SM_Sample", kind: "mesh", index: 0, size: 162_856 },
  { path: "tags/levels/b30/b30.scenario", kind: "tag", index: 0, size: 481_204 },
  { path: "tags/levels/a30/a30.scenario", kind: "tag", index: 1, size: 371_020 },
  { path: "tags/objects/characters/elite/elite.biped", kind: "tag", index: 0, size: 49_702 },
  { path: "tags/objects/characters/elite/elite.model", kind: "tag", index: 0, size: 12_880 },
  { path: "tags/objects/weapons/rifle/assault_rifle.weapon", kind: "tag", index: 0, size: 22_140 },
  {
    path: "textures/characters/Spartans/20thAnniv/Textures/T_Chief_Armor_20thAnniv_D",
    kind: "texture",
    index: 0,
    size: 4_818_220,
  },
  {
    path: "textures/characters/GuiltySpark/Textures/T_GuiltySpark_D",
    kind: "texture",
    index: 1,
    size: 6_371_884,
  },
  { path: "sounds/English(US)/12/100018565.wem", kind: "sound", index: 0, size: 310_629 },
  { path: "sounds/shared/10/243917884.wem", kind: "sound", index: 1, size: 21_689 },
];

/** Two sounds shaped like the real ones: one localised, one shared. */
const mockSounds = [
  {
    index: 0,
    path: "Media/English(US)/12/100018565.wem",
    language: "English(US)" as string | null,
    size: 310_629,
    channels: 2,
    sample_count: 728_342,
    avg_bytes_per_sec: 20_437,
    data_size: 310_511,
    event: "Play_b30_MusicStart" as string | null,
  },
  {
    index: 1,
    path: "Media/10/243917884.wem",
    language: null as string | null,
    size: 21_689,
    channels: 1,
    sample_count: 67_718,
    avg_bytes_per_sec: 15_284,
    data_size: 21_579,
    // Most media is not claimed by any event package, and shows as its ID.
    event: null as string | null,
  },
];

export const isTauri = "__TAURI_INTERNALS__" in window;

function field(partial: Partial<NodeView> & { name: string; type: string }): NodeView {
  return {
    kind: "field",
    offset: 0,
    size: 4,
    value: "",
    reference: null,
    options: [],
    selected: [],
    block: null,
    max_count: null,
    count: null,
    children: [],
    ...partial,
  };
}

function element(name: string, index: number, children: NodeView[]): NodeView {
  return {
    ...field({ name: `[${index}]`, type: "" }),
    kind: "element",
    children: [
      field({ name: "name", type: "string", value: `"${name}"`, size: 32 }),
      ...children,
    ],
  };
}

function block(
  name: string,
  blockName: string,
  max: number,
  children: NodeView[],
): NodeView {
  return {
    ...field({ name, type: "block", size: 12 }),
    kind: "block",
    block: blockName,
    max_count: max,
    count: children.length,
    children,
  };
}

const scenery = (i: number, x: number, y: number, z: number, yaw: number) => ({
  ...field({ name: `[${i}]`, type: "" }),
  kind: "element" as const,
  children: [
    field({
      name: "type",
      type: "short block index",
      value: `#${i % 2}`,
    }),
    field({ name: "name", type: "short block index", value: "none" }),
    field({
      name: "not placed",
      type: "word flags",
      options: ["automatically", "on easy", "on normal", "on hard"],
      selected: [],
      value: "0",
    }),
    field({ name: "desired permutation", type: "short integer", value: "0" }),
    field({
      name: "position",
      type: "real point 3d",
      value: `(${x}, ${y}, ${z})`,
      size: 12,
    }),
    field({
      name: "rotation",
      type: "real euler angles 3d",
      value: `(${yaw}, 0, 0)`,
      size: 12,
    }),
  ],
});

const mockTag: TagView = {
  path: "../../../Meteorite/Content/Tags/levels/b30/b30-scenario.ubulk",
  group: "scenario",
  four_cc: "scnr",
  version: 5,
  chunk_size: 481_204,
  data_size: 480_212,
  data_exact: true,
  error: null,
  node_count: 214,
  edited: [],
  history: { undo: 0, redo: 0 },
  fields: [
    block("skies", "sky_reference_block", 8, [
      {
        ...field({ name: "[0]", type: "" }),
        kind: "element",
        children: [
          field({
            name: "sky",
            type: "tag reference",
            value: "sky\\clear afternoon\\clear afternoon (sky )",
            reference: { group: "sky ", path: "sky\\clear afternoon\\clear afternoon" },
            size: 16,
          }),
        ],
      },
    ]),
    field({
      name: "type",
      type: "short enum",
      options: ["solo", "multiplayer", "main menu"],
      selected: ["solo"],
      value: "solo (0)",
    }),
    field({
      name: "flags",
      type: "word flags",
      options: ["cortana hack", "use demo UI", "disable color correction"],
      selected: [],
      value: "0",
    }),
    block("child scenarios", "scenario_child_scenario_block", 16, []),
    field({ name: "local north", type: "angle", value: "180" }),
    field({
      name: "music",
      type: "tag reference",
      value: "sound\\music\\demo\\mus_01 (lsnd)",
      reference: { group: "lsnd", path: "sound\\music\\demo\\mus_01" },
      size: 16,
    }),
    block("comments", "editor_comment_block", 1024, [
      element("dark", 0, [
        field({ name: "comment", type: "data", value: "34 bytes", size: 0 }),
      ]),
    ]),
    block("object names", "scenario_object_name_block", 640, [
      element("shafta_map_control", 0, []),
      element("shaftb_door_switch", 1, []),
    ]),
    block("scenery", "scenario_scenery_block", 2000, [
      scenery(0, 42.2008, 49.967, 4.5972, 81.3111),
      scenery(1, 44.1102, 51.202, 4.6104, -12.09),
      scenery(2, 39.8871, 47.5, 4.2, 173.4),
    ]),
    block("scenery palette", "scenario_scenery_palette_block", 100, [
      {
        ...field({ name: "[0]", type: "" }),
        kind: "element",
        children: [
          field({
            name: "name",
            type: "tag reference",
            value: "scenery\\tree_leafy\\tree_leafy (scen)",
            reference: { group: "scen", path: "scenery\\tree_leafy\\tree_leafy" },
            size: 16,
          }),
        ],
      },
    ]),
    field({
      name: "ambient color",
      type: "rgb color",
      value: "#6b7c8a",
      size: 12,
    }),
  ],
};

const mockGroups: GroupSummary[] = [
  { group: "biped", four_cc: "bipd", count: 32 },
  { group: "model", four_cc: "hlmt", count: 451 },
  { group: "scenario", four_cc: "scnr", count: 13 },
  { group: "vehicle", four_cc: "vehi", count: 25 },
  { group: "weapon", four_cc: "weap", count: 75 },
];

const mockTags: TagSummary[] = [
  { index: 0, group: "scenario", path: mockTag.path, short: "levels/b30/b30", size: 481_204 },
  { index: 1, group: "scenario", path: "", short: "levels/a30/a30", size: 371_020 },
  { index: 2, group: "model", path: "", short: "objects/sample/sample", size: 21_325 },
  // Preview-card targets: one per card kind, so hovering the sample model's
  // references in a browser exercises every branch.
  { index: 3, group: "scenery", path: "", short: "scenery/tree_leafy/tree_leafy", size: 8_420 },
  { index: 4, group: "sound", path: "", short: "sound/music/demo/mus_01", size: 1_204 },
];

/** A minimal hlmt view, so the Model segment is reachable in a browser. */
const mockModelTag: TagView = {
  path: "../../../Meteorite/Content/Tags/objects/sample/sample-model.ubulk",
  group: "model",
  four_cc: "hlmt",
  version: 27,
  chunk_size: 21_325,
  data_size: 20_988,
  data_exact: true,
  error: null,
  node_count: 12,
  edited: [],
  history: { undo: 0, redo: 0 },
  fields: [
    field({
      name: "collision model",
      type: "tag reference",
      value: "objects\\sample\\sample",
      reference: { group: "coll", path: "objects\\sample\\sample" },
      size: 16,
    }),
    field({
      name: "skeleton model",
      type: "tag reference",
      value: "objects\\sample\\sample",
      reference: { group: "skel", path: "objects\\sample\\sample" },
      size: 16,
    }),
    field({ name: "disappear distance", type: "real", value: "250" }),
  ],
};

const edits = new Map<string, string>();

/** Undo and redo for the mock, as snapshots of the edit map. */
const undoStack: Map<string, string>[] = [];
const redoStack: Map<string, string>[] = [];
function remember() {
  undoStack.push(new Map(edits));
  redoStack.length = 0;
}
function restore(from: Map<string, string>[], to: Map<string, string>[]) {
  const snapshot = from.pop();
  if (!snapshot) throw new Error("nothing to undo");
  to.push(new Map(edits));
  edits.clear();
  for (const [k, v] of snapshot) edits.set(k, v);
  return { undo: undoStack.length, redo: redoStack.length };
}

function withEdits(index = 0): TagView {
  const base = index === 2 ? mockModelTag : mockTag;
  return {
    ...base,
    edited: [...edits.keys()],
    history: { undo: undoStack.length, redo: redoStack.length },
  };
}

/**
 * A hand-written imitation of a scenario's script section, in the same shape
 * the real reader produces. Written for this mock, not extracted from the game.
 */
const mockScriptSource = `; startup script ============================================

; wake triggers on start
(script startup demo_start
	(ai_allegiance player human)
	(f_start_auto_save_loop)
	(wake music_demo)
	(sleep_until (= b_player_awake true) 1)
)

(global boolean b_player_awake false)
(global short s_wave_count 0)

(script static void (f_play_line (short delay) (ai character) (string debug_line))
	(print_if b_print_vo_lines debug_line)
	(if (>= (ai_living_count character) 1)
		(begin
			(set s_md_play_time (+ (ai_play_line character line) delay))
			(sleep s_md_play_time)
		)
		(print "vo info: character is not alive to speak")
	)
)

(script dormant music_demo
	(sound_looping_start "sound/music/demo/mus_01" none 1.0)
)
`;

export const mockApi = {
  detectInstall: async (): Promise<Install> => ({
    paks: "(mock)",
    oodle: "(mock)",
    note: "Running in a browser without Tauri; showing sample data.",
  }),
  openInstall: async () => ({ groups: mockGroups.length, tags: mockTags.length }),
  listGroups: async () => mockGroups,
  listTags: async (group: string) => mockTags.filter((t) => t.group === group),
  searchTags: async (query: string) =>
    mockTags.filter((t) => t.short.includes(query.toLowerCase())),
  readTag: async (index: number) => withEdits(index),
  readTagBytes: async () => [] as number[],
  // Resolution in the mock is by normalized path alone — enough to light up
  // both the resolved and the broken badge: the sample model's references and
  // the scenario's scenery/music match a mock tag, the sky does not.
  resolveRefs: async (refs: { group: string; path: string }[]) =>
    refs.map((r) => {
      if (r.path === "") return null;
      const want = r.path.replace(/\\/g, "/").toLowerCase();
      const hit = mockTags.find((t) => t.short === want);
      return hit
        ? { index: hit.index, group: hit.group, short: hit.short, size: hit.size }
        : null;
    }),
  peekTag: async (index: number) => {
    const t = mockTags.find((m) => m.index === index);
    const base = {
      group: t?.group ?? "scenario",
      four_cc: mockGroups.find((g) => g.group === t?.group)?.four_cc ?? "scnr",
      short: t?.short ?? "levels/b30/b30",
      chunk_size: t?.size ?? 0,
      texture: null as number | null,
      sound: null as number | null,
    };
    if (index === 2) return { ...base, preview: "model" as const };
    if (index === 3) return { ...base, preview: "texture" as const, texture: 0 };
    if (index === 4) return { ...base, preview: "sound" as const, sound: 1 };
    return { ...base, preview: "summary" as const };
  },
  referencingTags: async (index: number) => {
    // Slow enough that the first-scan spinner is reviewable in a browser.
    await new Promise((r) => setTimeout(r, 600));
    return mockTags.filter((t) => t.index !== index).slice(0, 2);
  },
  readMesh: async () => {
    // A textured-slot cube so the mesh viewer runs in a browser.
    const header = new TextEncoder().encode(
      JSON.stringify({
        path: "Env/Sample/SM_Sample",
        verts: 8,
        tris: 12,
        sections: [{ first_index: 0, num_triangles: 12, material: 0 }],
        materials: [
          { slot: "Base", texture: 0, texture_path: "T_Sample_D", material_path: "MI_Sample" },
        ],
        lod: 1,
        skeletal: false,
      }),
    );
    const pad = (4 - ((8 + header.length) % 4)) % 4;
    const verts = 8;
    const size = 8 + header.length + pad + verts * (12 + 12 + 8) + 12 * 3 * 4;
    const buffer = new ArrayBuffer(size);
    const view = new DataView(buffer);
    new Uint8Array(buffer).set(header, 8);
    view.setUint32(0, 0x48534d55, true);
    view.setUint32(4, header.length, true);
    let at = 8 + header.length + pad;
    const f32 = (v: number) => {
      view.setFloat32(at, v, true);
      at += 4;
    };
    const corners = [
      [-50, -50, -50], [50, -50, -50], [50, 50, -50], [-50, 50, -50],
      [-50, -50, 50], [50, -50, 50], [50, 50, 50], [-50, 50, 50],
    ];
    for (const c of corners) c.forEach(f32);
    for (let i = 0; i < corners.length; i++) [0, 0, 1].forEach(f32); // normals, close enough
    for (let v = 0; v < verts; v++) [v % 2, Math.floor(v / 2) % 2].forEach(f32);
    const tris = [
      0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
      2, 3, 7, 2, 7, 6, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5,
    ];
    for (const t of tris) {
      view.setUint32(at, t, true);
      at += 4;
    }
    return buffer;
  },
  readScenarioLayout: async () => ({
    layout: {
      bsps: ["levels\\halo1\\solo\\b30\\b30"],
      object_names: ["hog_one"],
      categories: [
        {
          block: "vehicles",
          group: "vehicle",
          palette: ["objects\\vehicles\\human\\warthog\\warthog"],
          placements: [
            {
              element: 0,
              palette: 0,
              name: 0,
              position: [2, 3, 0.6] as [number, number, number],
              rotation: [0.6, 0, 0] as [number, number, number],
              scale: 1,
            },
            {
              element: 1,
              palette: -1,
              name: -1,
              position: [-3, -2, 0.6] as [number, number, number],
              rotation: [0, 0, 0] as [number, number, number],
              scale: 1,
            },
          ],
        },
      ],
      trigger_volumes: [
        {
          name: "kill_ocean",
          position: [-6, -6, 0] as [number, number, number],
          forward: [1, 0, 0] as [number, number, number],
          up: [0, 0, 1] as [number, number, number],
          extents: [3, 3, 2] as [number, number, number],
        },
      ],
      squads: [
        {
          name: "covenant_beach",
          spawn_points: [
            { name: "", position: [4, -3, 0] as [number, number, number], facing: [1.2, 0] as [number, number] },
            { name: "", position: [5, -2, 0] as [number, number, number], facing: [2.1, 0] as [number, number] },
          ],
        },
      ],
      player_starts: [
        { position: [0, 0, 0] as [number, number, number], facing: [0.5, 0] as [number, number] },
      ],
    },
    bsp_indices: [0],
    palette_models: [[2]],
    palette_render: [[[]]],
  }),
  objectRenderModel: async () => [],
  readSbspWorld: async () => {
    // A 20×20 ground slab def instanced twice, so the world path renders in a
    // browser. Format mirrors geometry.rs `sbsp_world`.
    const defs = [{ verts: 4, tris: 2 }];
    const header = new TextEncoder().encode(
      JSON.stringify({ defs, world: null, instances: 2 }),
    );
    const headerPad = (4 - ((8 + header.length) % 4)) % 4;
    const size = 8 + header.length + headerPad + (4 * 12 + 2 * 12 + 2 * 4) + 2 * 56;
    const buffer = new ArrayBuffer(size);
    const view = new DataView(buffer);
    const bytes = new Uint8Array(buffer);
    view.setUint32(0, 0x50534253, true);
    view.setUint32(4, header.length, true);
    bytes.set(header, 8);
    let at = 8 + header.length + headerPad;
    const f32 = (v: number) => {
      view.setFloat32(at, v, true);
      at += 4;
    };
    const u32 = (v: number) => {
      view.setUint32(at, v, true);
      at += 4;
    };
    for (const [x, y] of [[-10, -10], [10, -10], [10, 10], [-10, 10]]) {
      f32(x);
      f32(y);
      f32(0);
    }
    [0, 1, 2, 0, 2, 3].forEach(u32);
    [0, 0].forEach(u32);
    for (const dx of [0, 20]) {
      u32(0);
      f32(1);
      [1, 0, 0, 0, 1, 0, 0, 0, 1].forEach(f32);
      f32(dx);
      f32(0);
      f32(0);
    }
    return buffer;
  },
  readModelGeometry: async () => {
    // A crate on a post: enough to exercise node posing, region filtering and
    // the skeleton overlay in a browser.
    const box = (w: number, h: number, d: number) => ({
      positions: [
        -w, -h, -d, w, -h, -d, w, h, -d, -w, h, -d,
        -w, -h, d, w, -h, d, w, h, d, -w, h, d,
      ],
      indices: [
        0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4,
        2, 3, 7, 2, 7, 6, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5,
      ],
    });
    const body = box(0.25, 0.25, 0.1);
    const head = box(0.12, 0.12, 0.08);
    return {
      collision: "objects/sample/sample",
      skeleton: "objects/sample/sample",
      meshes: [
        {
          region: "body",
          permutation: "default",
          node: 1,
          ...body,
          flags: body.indices.map(() => 0).slice(0, body.indices.length / 3),
        },
        {
          region: "head",
          permutation: "default",
          node: 2,
          ...head,
          flags: head.indices.map(() => 0).slice(0, head.indices.length / 3),
        },
      ],
      nodes: [
        { name: "b_pedestal", parent: -1, translation: [0, 0, 0], rotation: [0, 0, 0, 1] },
        { name: "b_body", parent: 0, translation: [0, 0, 0.3], rotation: [0, 0, 0, 1] },
        { name: "b_head", parent: 1, translation: [0, 0, 0.35], rotation: [0, 0, 0.383, 0.924] },
      ],
      marker_groups: [
        {
          name: "primary_trigger",
          markers: [{ node: 2, translation: [0.15, 0, 0], rotation: [0, 0, 0, 1] }],
        },
      ],
    };
  },
  setField: async (_index: number, path: string, value: string): Promise<EditResult> => {
    remember();
    edits.set(path, value);
    return { path, type: "field", before: "…", after: value, changed_bytes: 4 };
  },
  addElement: async (_index: number, path: string): Promise<EditResult> => {
    remember();
    edits.set(path, "add");
    return { path, type: "block", before: "0 element(s)", after: "1 element(s)", changed_bytes: 32 };
  },
  removeElement: async (_index: number, path: string, element: number): Promise<EditResult> => {
    remember();
    edits.set(path, `remove ${element}`);
    return { path, type: "block", before: "1 element(s)", after: "0 element(s)", changed_bytes: 32 };
  },
  duplicateElement: async (_index: number, path: string, element: number): Promise<EditResult> => {
    remember();
    edits.set(path, `duplicate ${element}`);
    return { path, type: "block", before: "1 element(s)", after: "2 element(s)", changed_bytes: 32 };
  },
  revertField: async (_index: number, path: string) => {
    remember();
    edits.delete(path);
    return edits.size;
  },
  revertTag: async () => {
    remember();
    edits.clear();
  },
  undoEdit: async () => restore(undoStack, redoStack),
  redoEdit: async () => restore(redoStack, undoStack),
  exportTag: async () => 0,
  listTextures: async (query: string) =>
    [
      { index: 0, path: "characters/Spartans/20thAnniv/Textures/T_Chief_Armor_20thAnniv_D", size: 4_818_220 },
      { index: 1, path: "characters/GuiltySpark/Textures/T_GuiltySpark_D", size: 6_371_884 },
    ].filter((t) => t.path.toLowerCase().includes(query.toLowerCase())),
  readTexture: async (index: number) => {
    const path =
      index === 0
        ? "characters/Spartans/20thAnniv/Textures/T_Chief_Armor_20thAnniv_D"
        : "characters/GuiltySpark/Textures/T_GuiltySpark_D";
    return {
      path,
      width: 512,
      height: 256,
      // The second one is BC7 so the unsupported-format path can be seen in a
      // browser without a game install.
      format: index === 0 ? "PF_DXT1" : "PF_BC7",
      mip: 0,
      num_mips: 10,
      png: swappedTextures.get(path) ?? mockTexturePng(),
      unsupported:
        index === 0
          ? null
          : "PF_BC7 cannot be written yet — it needs a BPTC encoder. Textures in " +
            "DXT1, DXT5, BC4, BC5 and the uncompressed formats can be swapped.",
      replaced: swappedTextures.has(path),
    };
  },
  readTextureThumb: async (index: number) => mockApi.readTexture(index),
  exportTexture: async () => 0,
  swapTexture: async (index: number) => {
    const path =
      index === 0
        ? "characters/Spartans/20thAnniv/Textures/T_Chief_Armor_20thAnniv_D"
        : "characters/GuiltySpark/Textures/T_GuiltySpark_D";
    const png = mockTexturePng();
    swappedTextures.set(path, png);
    // Slow enough that the busy state is visible in a browser.
    await new Promise((r) => setTimeout(r, 900));
    return { mips: 10, changed: 4_180_992, payload: 4_818_220, error: 2.41, png };
  },
  revertTexture: async (index: number) => {
    swappedTextures.delete(
      index === 0
        ? "characters/Spartans/20thAnniv/Textures/T_Chief_Armor_20thAnniv_D"
        : "characters/GuiltySpark/Textures/T_GuiltySpark_D",
    );
  },
  readScripts: async () => ({
    path: "levels/halo1/solo/demo/demo",
    source_files: [
      {
        name: "demo",
        text: mockScriptSource,
        lines: mockScriptSource.split(String.fromCharCode(10)).length,
        bytes: mockScriptSource.length,
        flags: [],
      },
    ],
    scripts: [
      { name: "demo_start", kind: "startup", return_type: "void", parameters: [], file: "demo", line: 4 },
      {
        name: "f_play_line",
        kind: "static",
        return_type: "void",
        parameters: ["short delay", "ai character", "string debug_line"],
        file: "demo",
        line: 14,
      },
      { name: "music_demo", kind: "dormant", return_type: "void", parameters: [], file: "demo", line: 25 },
      { name: "generated_branch_0", kind: "static", return_type: "void", parameters: [], file: null, line: null },
    ],
    globals: [
      {
        name: "b_player_awake",
        value_type: "boolean",
        initializer: "(global boolean b_player_awake false)",
        file: "demo",
        line: 11,
      },
      {
        name: "s_wave_count",
        value_type: "short",
        initializer: "(global short s_wave_count 0)",
        file: "demo",
        line: 12,
      },
    ],
    references: ["sound/music/demo/mus_01"],
    expressions: 148,
    datum_slots: 192,
    string_bytes: 1024,
    has_source: true,
    edited: false,
  }),
  compileScripts: async (_index: number, files: [string, string][]) => {
    // Enough of a compiler to exercise the interface: unbalanced parens are
    // the error a user actually hits while typing.
    const errors = files.flatMap(([, text]) =>
      text.split(String.fromCharCode(10)).flatMap((line, i) => {
        const depth =
          (line.match(/\(/g)?.length ?? 0) - (line.match(/\)/g)?.length ?? 0);
        return depth < -1
          ? [{ line: i + 1, message: "unmatched `)`" }]
          : [];
      })
    );
    return {
      ok: errors.length === 0,
      errors,
      warnings: [],
      scripts: 3,
      globals: 2,
      expressions: 148,
      tag_bytes: 4096,
      original_bytes: 4096,
      dropped: ["generated_branch_0"],
    };
  },
  setScripts: async () => ({
    ok: true,
    errors: [],
    warnings: [],
    scripts: 3,
    globals: 2,
    expressions: 148,
    tag_bytes: 4096,
    original_bytes: 4096,
    dropped: ["generated_branch_0"],
  }),
  revertScripts: async () => {},
  decompileScript: async (_index: number, name: string) =>
    `(script dormant ${name} (wake x))`,
  exportScript: async () => mockScriptSource.length,
  listSounds: async (query: string) =>
    mockSounds
      .map(({ index, path, language, size, event }) => ({
        index,
        path,
        language,
        size,
        event,
      }))
      .filter((s) => s.path.toLowerCase().includes(query.toLowerCase())),
  readSound: async (index: number) => {
    const s = mockSounds[index] ?? mockSounds[0];
    return {
      path: s.path,
      language: s.language,
      size: s.size,
      info: {
        codec: "Wwise Vorbis",
        format_tag: 0xffff,
        channels: s.channels,
        sample_rate: 48_000,
        avg_bytes_per_sec: s.avg_bytes_per_sec,
        sample_count: s.sample_count,
        duration_secs: s.sample_count / 48_000,
        data_size: s.data_size,
        chunks: ["fmt", "hash", "data"],
      },
      error: null,
      events: s.event
        ? [
            {
              name: s.event,
              package: "/Game/Audio/Music/WwiseEvents/Play_b30_MusicStart.uasset",
              sources: ["Music\\b30\\b30_MusicStart_01.wav"],
            },
          ]
        : [],
    };
  },
  exportSound: async () => 0,
  // A one-second sine as a WAV, so the player is exercisable outside Tauri.
  playSound: async () => ({ src: mockToneWav(), via: "mock tone", bytes: 88_244 }),
  listDir: async (path: string) => {
    const dir = path.replace(/^\/|\/$/g, "");
    const skip = dir === "" ? 0 : dir.length + 1;
    const dirs = new Map<string, { count: number; size: number }>();
    const files: DirEntry[] = [];
    for (const f of mockFiles) {
      if (dir !== "" && !f.path.startsWith(`${dir}/`)) continue;
      const rest = f.path.slice(skip);
      const cut = rest.indexOf("/");
      if (cut < 0) {
        files.push({ ...f, name: rest, children: null });
      } else {
        const name = rest.slice(0, cut);
        const e = dirs.get(name) ?? { count: 0, size: 0 };
        e.count += 1;
        e.size += f.size;
        dirs.set(name, e);
      }
    }
    const rows: DirEntry[] = [...dirs.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([name, e]) => ({
        name,
        path: dir === "" ? name : `${dir}/${name}`,
        kind: "dir" as const,
        index: null,
        size: e.size,
        children: e.count,
      }));
    files.sort((a, b) => a.name.localeCompare(b.name));
    return [...rows, ...files];
  },
  searchFiles: async (query: string) => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return mockFiles
      .filter((f) => f.path.toLowerCase().includes(q))
      .slice(0, 500)
      .map((f) => ({
        ...f,
        name: f.path.split("/").pop() ?? f.path,
        children: null,
      }));
  },

  // Enough links to exercise the collapsed state a real scenario triggers.
  tagLinks: async () => [
    {
      package: "/Game/Tags/objects/characters/elite/elite-model",
      kind: "tag" as const,
      index: 1,
      label: "elite (hlmt)",
    },
    {
      package: "/Game/characters/GuiltySpark/Textures/T_GuiltySpark_D",
      kind: "texture" as const,
      index: 1,
      label: "T_GuiltySpark_D",
    },
    ...Array.from({ length: 60 }, (_, i) => ({
      package: `/Game/Tags/sound/dialog/line_${i}-sound`,
      kind: "tag" as const,
      index: 0,
      label: `line_${i} (snd!)`,
    })),
    {
      package: "/Game/Blueprints/Synchronization/Characters/BP_EliteBipedActor",
      kind: "asset" as const,
      index: null,
      label: "BP_EliteBipedActor",
    },
  ],

  // A mock project so the mod panel can be built and reviewed in a browser.
  projectStatus: async () => mockProjectView(),
  projectNew: async (_dir: string, name: string, slug: string, version: string, summary: string) => {
    mockProject = { name, slug, version, summary };
    return mockProjectView()!;
  },
  projectOpen: async () => {
    mockProject = { name: "Faster Pistol", slug: "faster-pistol", version: "0.1.0", summary: "" };
    return mockProjectView()!;
  },
  projectClose: async () => {
    mockProject = null;
  },
  projectSetMeta: async (name: string, slug: string, version: string, summary: string) => {
    mockProject = { name, slug, version, summary };
    return mockProjectView()!;
  },
  projectRevert: async (_group: string, _tag: string, field: string | null) => {
    if (field === null) edits.clear();
    else edits.delete(field);
  },
  projectNewTag: async (_from: number, path: string, assetReference: string | null) => {
    const tag = path.replace(/\\/g, "/");
    const made: NewTagView = {
      group: "weapon",
      tag,
      from: "objects/weapons/pistol/pistol",
      asset_reference: assetReference,
      index: 2,
      edits: 0,
    };
    newTags.set(`weapon:${tag}`, made);
    return made;
  },
  projectRemoveNewTag: async (group: string, tag: string) => {
    newTags.delete(`${group}:${tag}`);
  },
  lastProject: async () => null,
  projectExport: async (): Promise<ExportView> => ({
    archive: "C:\\mods\\faster-pistol\\build\\faster-pistol-0.1.0.mjolnir",
    size: 18_432,
    containers: ["faster-pistol_P"],
    chunk_count: 1,
    resized: false,
    signed: true,
    signer_fingerprint: "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
    warnings: [],
  }),
  projectTest: async (): Promise<TestView> => ({
    files: [
      "pakchunk999-MJOLNIRDEV-faster-pistol_P.utoc",
      "pakchunk999-MJOLNIRDEV-faster-pistol_P.ucas",
      "pakchunk999-MJOLNIRDEV-faster-pistol_P.pak",
    ],
    resized: false,
    warnings: [],
  }),
  projectUntest: async () => 3,
  projectPublish: async (): Promise<PublishView> => ({
    slug: mockProject?.slug ?? "faster-pistol",
    version: mockProject?.version ?? "0.1.0",
    status: "published",
    findings: [{ level: "warning", code: "stray_container", message: "A sample finding." }],
    url: "https://mjolnircore.com/mods/faster-pistol",
  }),
  hubStatus: async (): Promise<HubStatus> => ({
    base: "https://mjolnircore.com",
    has_key: mockLinked,
    username: mockLinked ? "mock-author" : null,
  }),
  hubSetKey: async (key: string) => {
    mockLinked = key.trim().length > 0;
  },
  hubLinkStart: async (): Promise<LinkStart> => {
    mockPollsLeft = 2;
    return {
      user_code: "MOCK-CODE",
      verification_url: "https://mjolnircore.com/link?code=MOCK-CODE",
      interval: 1,
      expires_in: 600,
    };
  },
  // Approves itself after a couple of polls, so the waiting state is
  // reviewable without leaving the browser.
  hubLinkPoll: async (): Promise<LinkPoll> => {
    if (mockPollsLeft > 0) {
      mockPollsLeft -= 1;
      return { status: "pending", username: null };
    }
    mockLinked = true;
    return { status: "approved", username: "mock-author" };
  },
  hubUnlink: async () => {
    mockLinked = false;
  },
  signingStatus: async (): Promise<SigningStatus> => ({
    fingerprint: "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
    registered: null,
    label: "MOCK-DEVICE",
  }),
};

let mockProject: { name: string; slug: string; version: string; summary: string } | null = null;

/** Textures the mock mod replaces, by path, holding the replacement image. */
const swappedTextures = new Map<string, string>();
/** Tags the mock project adds, keyed `group:tag`. */
const newTags = new Map<string, NewTagView>();

/** Whether the mock editor is "linked", and how many polls until it is. */
let mockLinked = false;
let mockPollsLeft = 0;

function mockProjectView(): ProjectView | null {
  if (!mockProject) return null;
  return {
    root: "C:\\mods\\" + mockProject.slug,
    meta: { schema_version: 1, ...mockProject },
    changes:
      edits.size === 0
        ? []
        : [
            {
              group: "scenario",
              tag: "levels/b30/b30",
              index: 0,
              edits: [...edits.entries()].map(([field, value]) => ({
                field,
                value,
                before: "…",
                stale: false,
              })),
            },
          ],
    textures: [...swappedTextures.keys()].map((path) => ({
      path,
      index: 0,
      bytes: 4_818_220,
    })),
    new_tags: [...newTags.values()],
    test_files: [],
  };
}

/** A generated placeholder image so the viewer can be exercised in a browser. */
function mockTexturePng(): string {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 256;
  const ctx = canvas.getContext("2d")!;
  for (let y = 0; y < 4; y++) {
    for (let x = 0; x < 8; x++) {
      ctx.fillStyle = (x + y) % 2 ? "#3a4a2a" : "#d4a843";
      ctx.fillRect(x * 64, y * 64, 64, 64);
    }
  }
  ctx.fillStyle = "#0a0e17";
  ctx.font = "24px monospace";
  ctx.fillText("mock texture", 180, 132);
  return canvas.toDataURL("image/png");
}

/**
 * A one-second 440 Hz tone as a 16-bit mono WAV data URI, so the player and
 * its waveform can be exercised in a plain browser.
 */
function mockToneWav(): string {
  const rate = 44100;
  const frames = rate;
  const bytes = new ArrayBuffer(44 + frames * 2);
  const view = new DataView(bytes);
  const ascii = (at: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(at + i, s.charCodeAt(i));
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + frames * 2, true);
  ascii(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, frames * 2, true);
  for (let i = 0; i < frames; i++) {
    // Fade out, so the waveform has a shape rather than a solid block.
    const envelope = 1 - i / frames;
    view.setInt16(44 + i * 2, Math.sin((i / rate) * 440 * 2 * Math.PI) * 20000 * envelope, true);
  }
  let binary = "";
  for (const b of new Uint8Array(bytes)) binary += String.fromCharCode(b);
  return `data:audio/wav;base64,${btoa(binary)}`;
}
