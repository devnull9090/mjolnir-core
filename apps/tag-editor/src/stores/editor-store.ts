import { create } from "zustand";
import { api, type GroupSummary, type TagSummary, type TagView } from "../lib/api";

type Status = "idle" | "detecting" | "opening" | "ready" | "error";

type EditorState = {
  status: Status;
  error: string | null;
  paks: string | null;
  oodle: string | null;
  note: string | null;

  groups: GroupSummary[];
  selectedGroup: string | null;
  tags: TagSummary[];
  query: string;

  selectedTag: number | null;
  tag: TagView | null;
  tagLoading: boolean;

  detect: () => Promise<void>;
  open: (paks: string, oodle: string) => Promise<void>;
  selectGroup: (group: string) => Promise<void>;
  search: (query: string) => Promise<void>;
  selectTag: (index: number) => Promise<void>;
};

export const useEditor = create<EditorState>((set, get) => ({
  status: "idle",
  error: null,
  paks: null,
  oodle: null,
  note: null,

  groups: [],
  selectedGroup: null,
  tags: [],
  query: "",

  selectedTag: null,
  tag: null,
  tagLoading: false,

  async detect() {
    set({ status: "detecting", error: null });
    try {
      const found = await api.detectInstall();
      set({ paks: found.paks, oodle: found.oodle, note: found.note });
      if (found.paks && found.oodle) {
        await get().open(found.paks, found.oodle);
      } else {
        set({ status: "idle" });
      }
    } catch (e) {
      set({ status: "error", error: String(e) });
    }
  },

  async open(paks, oodle) {
    set({ status: "opening", error: null });
    try {
      await api.openInstall(paks, oodle);
      const groups = await api.listGroups();
      set({ status: "ready", groups, paks, oodle, note: null });
    } catch (e) {
      set({ status: "error", error: String(e) });
    }
  },

  async selectGroup(group) {
    set({ selectedGroup: group, query: "", tags: [] });
    try {
      set({ tags: await api.listTags(group) });
    } catch (e) {
      set({ error: String(e) });
    }
  },

  async search(query) {
    set({ query });
    if (!query.trim()) {
      const group = get().selectedGroup;
      set({ tags: group ? await api.listTags(group) : [] });
      return;
    }
    try {
      set({ tags: await api.searchTags(query) });
    } catch (e) {
      set({ error: String(e) });
    }
  },

  async selectTag(index) {
    set({ selectedTag: index, tagLoading: true, tag: null });
    try {
      set({ tag: await api.readTag(index), tagLoading: false });
    } catch (e) {
      set({ error: String(e), tagLoading: false });
    }
  },
}));
