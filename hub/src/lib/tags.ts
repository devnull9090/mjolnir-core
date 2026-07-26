import tagIndex from "@/generated/tag-index.json";
import tagDefs from "@/generated/tag-defs.json";

/** Field types that are structural and carry no user-visible value. */
const HIDDEN_TYPES = new Set(["pad", "terminator X", "custom"]);

export type TagField = {
  name: string;
  type: string;
  offset?: number;
  size?: number;
  options?: string[];
  block?: { name: string; max_count: number };
  struct_index?: number;
  array_count?: number;
};

export type TagStruct = {
  name: string;
  guid?: string;
  size?: number;
  fields: TagField[];
};

export type TagGroupDef = {
  group: string;
  name: string;
  version: number;
  tag_count: number;
  structs: TagStruct[];
};

export type TagGroupSummary = {
  slug: string;
  name: string;
  group: string;
  version: number;
  tagCount: number;
  structs: number;
  fields: number;
  visible: number;
  size: number | null;
};

type TagIndex = {
  generator: string;
  build: string;
  groups: TagGroupSummary[];
};

type TagDefs = {
  generator: string;
  build: string;
  groups: Record<string, TagGroupDef>;
};

const index = tagIndex as TagIndex;
const defs = tagDefs as unknown as TagDefs;

export function getBuild(): string {
  return index.build;
}

/** Every group summary, sorted by name. */
export function getTagGroups(): TagGroupSummary[] {
  return index.groups;
}

export function getTagGroupSummary(slug: string): TagGroupSummary | undefined {
  return index.groups.find((g) => g.slug === slug);
}

/** The full definition for one group, or undefined if the slug is unknown. */
export function getTagGroup(slug: string): TagGroupDef | undefined {
  const summary = getTagGroupSummary(slug);
  return summary ? defs.groups[summary.name] : undefined;
}

export function isHiddenType(type: string): boolean {
  return HIDDEN_TYPES.has(type);
}

/** Totals for the reference landing page. */
export function getTotals() {
  const groups = index.groups;
  return {
    groups: groups.length,
    tags: groups.reduce((n, g) => n + g.tagCount, 0),
    structs: groups.reduce((n, g) => n + g.structs, 0),
    fields: groups.reduce((n, g) => n + g.visible, 0),
  };
}
