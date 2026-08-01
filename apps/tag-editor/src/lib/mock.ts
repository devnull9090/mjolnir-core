/**
 * In-browser stand-in for the Tauri backend, active only when the app runs
 * outside Tauri (plain `vite dev`). It exists so the interface can be built
 * and reviewed without a game installation; the data is a small hand-written
 * imitation of a scenario tag and is not shipped content.
 */
import type {
  EditResult,
  GroupSummary,
  Install,
  NodeView,
  TagSummary,
  TagView,
} from "./api";

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
};

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
