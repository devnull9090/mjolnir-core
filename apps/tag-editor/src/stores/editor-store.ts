import { create } from "zustand";
import {
  api,
  type EditResult,
  type GroupSummary,
  type TagSummary,
  type TagView,
} from "../lib/api";

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
  /** The last edit applied, so the UI can confirm what it did. */
  lastEdit: EditResult | null;
  editError: string | null;

  detect: () => Promise<void>;
  open: (paks: string, oodle: string) => Promise<void>;
  selectGroup: (group: string) => Promise<void>;
  search: (query: string) => Promise<void>;
  selectTag: (index: number) => Promise<void>;
  setField: (path: string, value: string) => Promise<boolean>;
  revertField: (path: string) => Promise<void>;
  revertTag: () => Promise<void>;
  exportTag: (dest: string) => Promise<number | null>;
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
  lastEdit: null,
  editError: null,

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
    set({ selectedTag: index, tagLoading: true, tag: null, lastEdit: null, editError: null });
    try {
      set({ tag: await api.readTag(index), tagLoading: false });
    } catch (e) {
      set({ error: String(e), tagLoading: false });
    }
  },

  async setField(path, value) {
    const index = get().selectedTag;
    if (index === null) return false;
    try {
      const lastEdit = await api.setField(index, path, value);
      // Re-read so every view of the tag reflects the change, not just this row.
      set({ lastEdit, editError: null, tag: await api.readTag(index) });
      return true;
    } catch (e) {
      set({ editError: String(e), lastEdit: null });
      return false;
    }
  },

  async revertField(path) {
    const index = get().selectedTag;
    if (index === null) return;
    await api.revertField(index, path);
    set({ tag: await api.readTag(index), lastEdit: null, editError: null });
  },

  async revertTag() {
    const index = get().selectedTag;
    if (index === null) return;
    await api.revertTag(index);
    set({ tag: await api.readTag(index), lastEdit: null, editError: null });
  },

  async exportTag(dest) {
    const index = get().selectedTag;
    if (index === null) return null;
    try {
      const written = await api.exportTag(index, dest);
      set({ editError: null });
      return written;
    } catch (e) {
      set({ editError: String(e) });
      return null;
    }
  },
}));
