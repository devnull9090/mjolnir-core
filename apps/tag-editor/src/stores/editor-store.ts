import { create } from "zustand";
import {
  api,
  type EditResult,
  type GroupSummary,
  type TagSummary,
  type TagView,
  type TextureSummary,
  type TextureView,
} from "../lib/api";

type Status = "idle" | "detecting" | "opening" | "ready" | "error";

export type ViewMode = "form" | "tree";

const VIEW_KEY = "tag-editor-view";

function storedViewMode(): ViewMode {
  return localStorage.getItem(VIEW_KEY) === "tree" ? "tree" : "form";
}

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

  /** How the inspector renders: Guerilla-style form or a flat field tree. */
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;

  /** What the left panel browses: Blam tags or Unreal texture assets. */
  browse: "tags" | "textures";
  setBrowse: (browse: "tags" | "textures") => void;
  textures: TextureSummary[];
  textureQuery: string;
  searchTextures: (query: string) => Promise<void>;
  selectedTexture: number | null;
  texture: TextureView | null;
  textureLoading: boolean;
  textureError: string | null;
  selectTexture: (index: number) => Promise<void>;
  exportTexture: (dest: string) => Promise<number | null>;

  detect: () => Promise<void>;
  open: (paks: string, oodle: string) => Promise<void>;
  selectGroup: (group: string) => Promise<void>;
  search: (query: string) => Promise<void>;
  selectTag: (index: number) => Promise<void>;
  setField: (path: string, value: string) => Promise<boolean>;
  /** Jump to the tag a reference points at, given its four-CC and Blam path. */
  followReference: (fourCc: string, path: string) => Promise<boolean>;
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

  viewMode: storedViewMode(),
  setViewMode(mode) {
    localStorage.setItem(VIEW_KEY, mode);
    set({ viewMode: mode });
  },

  browse: "tags",
  setBrowse(browse) {
    set({ browse });
    if (browse === "textures" && get().textures.length === 0) {
      void get().searchTextures("");
    }
  },
  textures: [],
  textureQuery: "",
  async searchTextures(query) {
    set({ textureQuery: query });
    try {
      set({ textures: await api.listTextures(query) });
    } catch (e) {
      set({ error: String(e) });
    }
  },
  selectedTexture: null,
  texture: null,
  textureLoading: false,
  textureError: null,
  async selectTexture(index) {
    set({ selectedTexture: index, textureLoading: true, texture: null, textureError: null });
    try {
      set({ texture: await api.readTexture(index), textureLoading: false });
    } catch (e) {
      set({ textureError: String(e), textureLoading: false });
    }
  },
  async exportTexture(dest) {
    const index = get().selectedTexture;
    if (index === null) return null;
    try {
      return await api.exportTexture(index, dest);
    } catch (e) {
      set({ textureError: String(e) });
      return null;
    }
  },

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

  async followReference(fourCc, path) {
    // The reference stores a four-CC and a Blam path with backslashes; the
    // catalog stores group directory names and forward slashes.
    const group = get()
      .groups.find((g) => g.four_cc.trim() === fourCc.trim())
      ?.group;
    const want = path.replace(/\\/g, "/").toLowerCase();
    const tail = want.split("/").pop() ?? want;
    try {
      const results = await api.searchTags(tail);
      const hit =
        results.find(
          (t) => t.short.toLowerCase() === want && (!group || t.group === group),
        ) ??
        results.find(
          (t) =>
            t.short.toLowerCase().endsWith(want) && (!group || t.group === group),
        );
      if (!hit) return false;
      if (hit.group !== get().selectedGroup) {
        await get().selectGroup(hit.group);
      }
      await get().selectTag(hit.index);
      return true;
    } catch {
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
