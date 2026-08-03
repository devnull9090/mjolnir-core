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
  NodeView,
  ProjectView,
  PublishView,
  TagSummary,
  TagView,
  TestView,
} from "./api";

/** A slice of the virtual filesystem, shaped like the real one. */
const mockFiles: Omit<DirEntry, "name" | "children">[] = [
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
  { group: "scenario", four_cc: "scnr", count: 13 },
  { group: "vehicle", four_cc: "vehi", count: 25 },
  { group: "weapon", four_cc: "weap", count: 75 },
];

const mockTags: TagSummary[] = [
  { index: 0, group: "scenario", path: mockTag.path, short: "levels/b30/b30", size: 481_204 },
  { index: 1, group: "scenario", path: "", short: "levels/a30/a30", size: 371_020 },
];

const edits = new Map<string, string>();

function withEdits(): TagView {
  return { ...mockTag, edited: [...edits.keys()] };
}

export const mockApi = {
  detectInstall: async (): Promise<Install> => ({
    paks: "(mock)",
    oodle: "(mock)",
    note: "Running in a browser without Tauri; showing sample data.",
  }),
  openInstall: async () => ({ groups: mockGroups.length, tags: mockTags.length }),
  listGroups: async () => mockGroups,
  listTags: async (group: string) =>
    group === "scenario" ? mockTags : ([] as TagSummary[]),
  searchTags: async (query: string) =>
    mockTags.filter((t) => t.short.includes(query.toLowerCase())),
  readTag: async () => withEdits(),
  readTagBytes: async () => [] as number[],
  setField: async (_index: number, path: string, value: string): Promise<EditResult> => {
    edits.set(path, value);
    return { path, type: "field", before: "…", after: value, changed_bytes: 4 };
  },
  revertField: async (_index: number, path: string) => {
    edits.delete(path);
    return edits.size;
  },
  revertTag: async () => {
    edits.clear();
  },
  exportTag: async () => 0,
  listTextures: async (query: string) =>
    [
      { index: 0, path: "characters/Spartans/20thAnniv/Textures/T_Chief_Armor_20thAnniv_D", size: 4_818_220 },
      { index: 1, path: "characters/GuiltySpark/Textures/T_GuiltySpark_D", size: 6_371_884 },
    ].filter((t) => t.path.toLowerCase().includes(query.toLowerCase())),
  readTexture: async (index: number) => ({
    path: index === 0 ? "characters/Spartans/20thAnniv/Textures/T_Chief_Armor_20thAnniv_D" : "characters/GuiltySpark/Textures/T_GuiltySpark_D",
    width: 512,
    height: 256,
    format: "PF_DXT1",
    mip: 0,
    num_mips: 10,
    png: mockTexturePng(),
  }),
  exportTexture: async () => 0,
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
  lastProject: async () => null,
  projectExport: async (): Promise<ExportView> => ({
    archive: "C:\\mods\\faster-pistol\\build\\faster-pistol-0.1.0.mjolnir",
    size: 18_432,
    containers: ["faster-pistol_P"],
    chunk_count: 1,
    resized: false,
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
  hubStatus: async (): Promise<HubStatus> => ({ base: "https://mjolnircore.com", has_key: false }),
  hubSetKey: async () => {},
};

let mockProject: { name: string; slug: string; version: string; summary: string } | null = null;

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
