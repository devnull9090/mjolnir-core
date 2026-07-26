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

export type FieldView = {
  name: string;
  type: string;
  offset: number | null;
  size: number | null;
  options: string[];
  block: string | null;
  max_count: number | null;
};

export type StructView = {
  name: string;
  size: number | null;
  fields: FieldView[];
};

export type TagView = {
  path: string;
  group: string;
  four_cc: string;
  version: number;
  chunk_size: number;
  data_size: number;
  data_exact: boolean;
  structs: StructView[];
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
