import { invoke } from "@tauri-apps/api/core";

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
  fields: NodeView[];
};

export const api = {
  detectInstall: () => invoke<Install>("detect_install"),
  openInstall: (paks: string, oodle: string) =>
    invoke<{ groups: number; tags: number }>("open_install", { paks, oodle }),
  listGroups: () => invoke<GroupSummary[]>("list_groups"),
  listTags: (group: string) => invoke<TagSummary[]>("list_tags", { group }),
  searchTags: (query: string) => invoke<TagSummary[]>("search_tags", { query }),
  readTag: (index: number) => invoke<TagView>("read_tag", { index }),
  readTagBytes: (index: number, limit = 4096) =>
    invoke<number[]>("read_tag_bytes", { index, limit }),
};
