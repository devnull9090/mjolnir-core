import { invoke } from "@tauri-apps/api/core";
import { isTauri, mockApi } from "./mock";

export type Install = {
  paks: string | null;
  oodle: string | null;
  note: string | null;
};

export type GroupSummary = {
  group: string;
  four_cc: string;
  count: number;
};

export type TagSummary = {
  index: number;
  group: string;
  path: string;
  short: string;
  size: number;
};

export type NodeKind = "field" | "struct" | "block" | "element" | "array";

export type Reference = {
  group: string;
  path: string;
};

export type NodeView = {
  kind: NodeKind;
  name: string;
  type: string;
  offset: number;
  size: number;
  /** Rendered value; empty when there is nothing to show. */
  value: string;
  reference: Reference | null;
  /** Every option an enum or bitfield can take, in declaration order. */
  options: string[];
  /** Which options are actually set on this field. */
  selected: string[];
  block: string | null;
  max_count: number | null;
  /** Elements this block really has; `children` may hold fewer. */
  count: number | null;
  children: NodeView[];
};

export type TagView = {
  path: string;
  group: string;
  four_cc: string;
  version: number;
  chunk_size: number;
  data_size: number;
  data_exact: boolean;
  /** Why the values could not be read, when they could not be. */
  error: string | null;
  node_count: number;
  /** Field paths with an unexported edit. */
  edited: string[];
  fields: NodeView[];
};

export type TextureSummary = {
  index: number;
  path: string;
  size: number;
};

export type TextureView = {
  path: string;
  width: number;
  height: number;
  format: string;
  /** The mip that was decoded; 0 unless the full size was too large to ship over IPC. */
  mip: number;
  num_mips: number;
  /** Data URI, ready for an img tag. */
  png: string;
};

/** One package a tag imports, resolved to something openable when possible. */
export type LinkedAsset = {
  package: string;
  kind: "tag" | "texture" | "asset";
  index: number | null;
  label: string;
};

export type EditResult = {
  path: string;
  type: string;
  before: string;
  after: string;
  /** Bytes of the file that changed; 0 when the value was already that. */
  changed_bytes: number;
};

const tauriApi = {
  detectInstall: () => invoke<Install>("detect_install"),
  openInstall: (paks: string, oodle: string) =>
    invoke<{ groups: number; tags: number }>("open_install", { paks, oodle }),
  listGroups: () => invoke<GroupSummary[]>("list_groups"),
  listTags: (group: string) => invoke<TagSummary[]>("list_tags", { group }),
  searchTags: (query: string) => invoke<TagSummary[]>("search_tags", { query }),
  readTag: (index: number) => invoke<TagView>("read_tag", { index }),
  readTagBytes: (index: number, limit = 4096) =>
    invoke<number[]>("read_tag_bytes", { index, limit }),
  setField: (index: number, path: string, value: string) =>
    invoke<EditResult>("set_field", { index, path, value }),
  revertField: (index: number, path: string) =>
    invoke<number>("revert_field", { index, path }),
  revertTag: (index: number) => invoke<void>("revert_tag", { index }),
  exportTag: (index: number, dest: string) =>
    invoke<number>("export_tag", { index, dest }),
  listTextures: (query: string) =>
    invoke<TextureSummary[]>("list_textures", { query }),
  readTexture: (index: number) => invoke<TextureView>("read_texture", { index }),
  exportTexture: (index: number, dest: string) =>
    invoke<number>("export_texture", { index, dest }),
  tagLinks: (index: number) => invoke<LinkedAsset[]>("tag_links", { index }),
};

export type Api = typeof tauriApi;

/**
 * Outside Tauri (plain `vite dev`) the IPC bridge does not exist, so a mock
 * with sample data stands in and the interface can be reviewed in a browser.
 */
export const api: Api = isTauri ? tauriApi : (mockApi as unknown as Api);
