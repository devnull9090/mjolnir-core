import { create } from "zustand";
import {
  api,
  type DirEntry,
  type EditResult,
  type ExportView,
  type GroupSummary,
  type HubStatus,
  type LinkedAsset,
  type ProjectView,
  type PublishView,
  type TagSummary,
  type TagView,
  type TestView,
  type TextureSummary,
  type TextureView,
} from "../lib/api";

type Status = "idle" | "detecting" | "opening" | "ready" | "error";

export type ViewMode = "form" | "tree";

/** One open document: a tag or a texture, shown as a tab. */
export type Tab = {
  id: number;
  kind: "tag" | "texture";
  /** Catalog index within its kind. */
  index: number;
  label: string;
};

const VIEW_KEY = "tag-editor-view";

function storedViewMode(): ViewMode {
  return localStorage.getItem(VIEW_KEY) === "tree" ? "tree" : "form";
}

/** Decoded textures kept per tab; bounded because the PNGs are large. */
const TEXTURE_CACHE_MAX = 8;

let nextTabId = 1;

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

  /** Open documents and the one currently shown. */
  tabs: Tab[];
  activeTab: number | null;
  openTab: (kind: Tab["kind"], index: number, label: string) => Promise<void>;
  activateTab: (id: number) => Promise<void>;
  closeTab: (id: number) => void;
  /** Tag indices with unexported edits, for the tab dirty markers. */
  dirtyTags: Record<number, boolean>;

  selectedTag: number | null;
  tag: TagView | null;
  tagLoading: boolean;
  /** Packages the current tag imports, resolved to openable things. */
  tagLinks: LinkedAsset[];
  /** The last edit applied, so the UI can confirm what it did. */
  lastEdit: EditResult | null;
  editError: string | null;

  /** How the inspector renders: Guerilla-style form or a flat field tree. */
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;

  /** What the left panel browses: assets, tag groups, textures, or the mod. */
  browse: "files" | "tags" | "textures" | "mod";
  setBrowse: (browse: "files" | "tags" | "textures" | "mod") => void;

  /** The open mod project; edits autosave into it while one is open. */
  project: ProjectView | null;
  projectError: string | null;
  /** Which long-running mod action is in flight, to disable its button. */
  projectBusy: "export" | "test" | "untest" | "publish" | null;
  exportResult: ExportView | null;
  testResult: TestView | null;
  publishResult: PublishView | null;
  hub: HubStatus | null;
  refreshProject: () => Promise<void>;
  newProject: (
    dir: string,
    name: string,
    slug: string,
    version: string,
    summary: string,
  ) => Promise<boolean>;
  openProject: (dir: string) => Promise<boolean>;
  closeProject: () => Promise<void>;
  saveProjectMeta: (
    name: string,
    slug: string,
    version: string,
    summary: string,
  ) => Promise<boolean>;
  /** Revert by identity, so stale edits without a catalog index can go too. */
  revertProjectEdit: (group: string, tag: string, field: string | null) => Promise<void>;
  exportMod: () => Promise<void>;
  testMod: () => Promise<void>;
  untestMod: () => Promise<void>;
  publishMod: (changelog: string) => Promise<void>;
  loadHub: () => Promise<void>;
  setHubKey: (key: string) => Promise<boolean>;

  /** Virtual filesystem browser: current directory and its listing. */
  dir: string;
  entries: DirEntry[];
  dirLoading: boolean;
  fileQuery: string;
  openDir: (path: string) => Promise<void>;
  searchFiles: (query: string) => Promise<void>;
  textures: TextureSummary[];
  textureQuery: string;
  searchTextures: (query: string) => Promise<void>;
  selectedTexture: number | null;
  texture: TextureView | null;
  textureLoading: boolean;
  textureError: string | null;
  exportTexture: (dest: string) => Promise<number | null>;

  detect: () => Promise<void>;
  open: (paks: string, oodle: string) => Promise<void>;
  selectGroup: (group: string) => Promise<void>;
  search: (query: string) => Promise<void>;
  setField: (path: string, value: string) => Promise<boolean>;
  /** Open the tag a reference points at, given its four-CC and Blam path. */
  followReference: (fourCc: string, path: string) => Promise<boolean>;
  revertField: (path: string) => Promise<void>;
  revertTag: () => Promise<void>;
  exportTag: (dest: string) => Promise<number | null>;
};

/** Tab label for a tag: Guerilla-style `name.group`. */
export function tagLabel(t: { short: string; group: string }): string {
  const tail = t.short.split("/").pop() ?? t.short;
  return `${tail}.${t.group}`;
}

const textureCache = new Map<number, TextureView>();

export const useEditor = create<EditorState>((set, get) => {
  /** Load a tag into the active-content slots. */
  async function loadTag(index: number) {
    set({
      selectedTag: index,
      selectedTexture: null,
      tagLoading: true,
      tag: null,
      tagLinks: [],
      lastEdit: null,
      editError: null,
    });
    try {
      const tag = await api.readTag(index);
      set((s) => ({
        tag,
        tagLoading: false,
        dirtyTags: { ...s.dirtyTags, [index]: tag.edited.length > 0 },
      }));
    } catch (e) {
      set({ error: String(e), tagLoading: false });
      return;
    }
    // The import links arrive after the tag; they never block it.
    try {
      const links = await api.tagLinks(index);
      if (get().selectedTag === index) set({ tagLinks: links });
    } catch {
      // A tag without a readable package header simply shows no links.
    }
  }

  /** Load a texture into the active-content slots, via the cache. */
  async function loadTexture(index: number) {
    set({ selectedTexture: index, selectedTag: null, textureError: null });
    const cached = textureCache.get(index);
    if (cached) {
      set({ texture: cached, textureLoading: false });
      return;
    }
    set({ textureLoading: true, texture: null });
    try {
      const texture = await api.readTexture(index);
      textureCache.set(index, texture);
      while (textureCache.size > TEXTURE_CACHE_MAX) {
        const oldest = textureCache.keys().next().value;
        if (oldest === undefined) break;
        textureCache.delete(oldest);
      }
      // Only show it if this tab is still the active one.
      if (get().selectedTexture === index) {
        set({ texture, textureLoading: false });
      }
    } catch (e) {
      if (get().selectedTexture === index) {
        set({ textureError: String(e), textureLoading: false });
      }
    }
  }

  /** Re-read the active tag after project-level changes touch its edits. */
  async function refreshActiveTag() {
    const { tabs, activeTab } = get();
    const tab = tabs.find((t) => t.id === activeTab);
    if (!tab || tab.kind !== "tag") return;
    try {
      const tag = await api.readTag(tab.index);
      set((s) => ({
        tag,
        dirtyTags: { ...s.dirtyTags, [tab.index]: tag.edited.length > 0 },
      }));
    } catch {
      // The next explicit load will report whatever went wrong.
    }
  }

  return {
    // Detection starts as soon as the app mounts, so that is the honest
    // starting state; `idle` means detection ran and found nothing.
    status: "detecting",
    error: null,
    paks: null,
    oodle: null,
    note: null,

    groups: [],
    selectedGroup: null,
    tags: [],
    query: "",

    tabs: [],
    activeTab: null,
    dirtyTags: {},

    async openTab(kind, index, label) {
      const existing = get().tabs.find((t) => t.kind === kind && t.index === index);
      if (existing) {
        await get().activateTab(existing.id);
        return;
      }
      const tab: Tab = { id: nextTabId++, kind, index, label };
      set((s) => ({ tabs: [...s.tabs, tab] }));
      await get().activateTab(tab.id);
    },

    async activateTab(id) {
      const tab = get().tabs.find((t) => t.id === id);
      if (!tab) return;
      set({ activeTab: id });
      if (tab.kind === "tag") {
        await loadTag(tab.index);
      } else {
        await loadTexture(tab.index);
      }
    },

    closeTab(id) {
      const { tabs, activeTab } = get();
      const at = tabs.findIndex((t) => t.id === id);
      if (at < 0) return;
      const next = tabs.filter((t) => t.id !== id);
      set({ tabs: next });
      if (activeTab !== id) return;
      const neighbor = next[Math.min(at, next.length - 1)];
      if (neighbor) {
        void get().activateTab(neighbor.id);
      } else {
        set({
          activeTab: null,
          selectedTag: null,
          tag: null,
          tagLinks: [],
          selectedTexture: null,
          texture: null,
          textureError: null,
          lastEdit: null,
          editError: null,
        });
      }
    },

    selectedTag: null,
    tag: null,
    tagLoading: false,
    tagLinks: [],
    lastEdit: null,
    editError: null,

    viewMode: storedViewMode(),
    setViewMode(mode) {
      localStorage.setItem(VIEW_KEY, mode);
      set({ viewMode: mode });
    },

    browse: "files",
    setBrowse(browse) {
      set({ browse });
      if (browse === "textures" && get().textures.length === 0) {
        void get().searchTextures("");
      }
      if (browse === "files" && get().entries.length === 0 && !get().fileQuery) {
        void get().openDir(get().dir);
      }
    },

    dir: "",
    entries: [],
    dirLoading: false,
    fileQuery: "",
    async openDir(path) {
      // Navigating leaves any search behind, the way a file dialog does.
      set({ dir: path, fileQuery: "", dirLoading: true });
      try {
        set({ entries: await api.listDir(path), dirLoading: false });
      } catch (e) {
        set({ error: String(e), dirLoading: false });
      }
    },
    async searchFiles(query) {
      set({ fileQuery: query });
      if (!query.trim()) {
        await get().openDir(get().dir);
        return;
      }
      set({ dirLoading: true });
      try {
        set({ entries: await api.searchFiles(query), dirLoading: false });
      } catch (e) {
        set({ error: String(e), dirLoading: false });
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
        // The DLL is optional; without one the backend uses its own decoder.
        if (found.paks) {
          await get().open(found.paks, found.oodle ?? "");
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
        // `dirLoading` goes up with the shell so the file list shows its
        // spinner instead of "Empty." for the frame before the root arrives.
        set({ status: "ready", groups, paks, oodle, note: null, dirLoading: true });
        // The asset tree is the default view, so it is ready on arrival.
        await get().openDir("");
      } catch (e) {
        set({ status: "error", error: String(e) });
        return;
      }
      // Resume the mod project from the last session, so closing the editor
      // never loses work. A failure shows in the mod panel, not as a wall.
      try {
        const dir = await api.lastProject();
        if (dir) await get().openProject(dir);
      } catch (e) {
        set({ projectError: String(e) });
      }
      void get().loadHub();
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

    async setField(path, value) {
      const index = get().selectedTag;
      if (index === null) return false;
      try {
        const lastEdit = await api.setField(index, path, value);
        // Re-read so every view of the tag reflects the change, not just
        // this row.
        const tag = await api.readTag(index);
        set((s) => ({
          lastEdit,
          editError: null,
          tag,
          dirtyTags: { ...s.dirtyTags, [index]: tag.edited.length > 0 },
        }));
        if (get().project) void get().refreshProject();
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
        await get().openTab("tag", hit.index, tagLabel(hit));
        return true;
      } catch {
        return false;
      }
    },

    async revertField(path) {
      const index = get().selectedTag;
      if (index === null) return;
      await api.revertField(index, path);
      const tag = await api.readTag(index);
      set((s) => ({
        tag,
        lastEdit: null,
        editError: null,
        dirtyTags: { ...s.dirtyTags, [index]: tag.edited.length > 0 },
      }));
      if (get().project) void get().refreshProject();
    },

    async revertTag() {
      const index = get().selectedTag;
      if (index === null) return;
      await api.revertTag(index);
      const tag = await api.readTag(index);
      set((s) => ({
        tag,
        lastEdit: null,
        editError: null,
        dirtyTags: { ...s.dirtyTags, [index]: false },
      }));
      if (get().project) void get().refreshProject();
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

    project: null,
    projectError: null,
    projectBusy: null,
    exportResult: null,
    testResult: null,
    publishResult: null,
    hub: null,

    async refreshProject() {
      try {
        set({ project: await api.projectStatus() });
      } catch (e) {
        set({ projectError: String(e) });
      }
    },

    async newProject(dir, name, slug, version, summary) {
      try {
        const project = await api.projectNew(dir, name, slug, version, summary);
        set({
          project,
          projectError: null,
          exportResult: null,
          testResult: null,
          publishResult: null,
        });
        return true;
      } catch (e) {
        set({ projectError: String(e) });
        return false;
      }
    },

    async openProject(dir) {
      try {
        const project = await api.projectOpen(dir);
        set({
          project,
          projectError: null,
          exportResult: null,
          testResult: null,
          publishResult: null,
        });
        // Opening a project replaces the working edits, so every open tab
        // must reflect the recipe rather than whatever came before.
        await refreshActiveTag();
        return true;
      } catch (e) {
        set({ projectError: String(e) });
        return false;
      }
    },

    async closeProject() {
      try {
        await api.projectClose();
        set({
          project: null,
          projectError: null,
          exportResult: null,
          testResult: null,
          publishResult: null,
          dirtyTags: {},
        });
        await refreshActiveTag();
      } catch (e) {
        set({ projectError: String(e) });
      }
    },

    async saveProjectMeta(name, slug, version, summary) {
      try {
        const project = await api.projectSetMeta(name, slug, version, summary);
        set({ project, projectError: null });
        return true;
      } catch (e) {
        set({ projectError: String(e) });
        return false;
      }
    },

    async revertProjectEdit(group, tag, field) {
      try {
        await api.projectRevert(group, tag, field);
        set({ projectError: null });
        await get().refreshProject();
        await refreshActiveTag();
      } catch (e) {
        set({ projectError: String(e) });
      }
    },

    async exportMod() {
      set({ projectBusy: "export", exportResult: null, projectError: null });
      try {
        set({ exportResult: await api.projectExport() });
      } catch (e) {
        set({ projectError: String(e) });
      } finally {
        set({ projectBusy: null });
      }
    },

    async testMod() {
      set({ projectBusy: "test", testResult: null, projectError: null });
      try {
        set({ testResult: await api.projectTest() });
      } catch (e) {
        set({ projectError: String(e) });
      } finally {
        set({ projectBusy: null });
        void get().refreshProject();
      }
    },

    async untestMod() {
      set({ projectBusy: "untest", projectError: null });
      try {
        await api.projectUntest();
        set({ testResult: null });
      } catch (e) {
        set({ projectError: String(e) });
      } finally {
        set({ projectBusy: null });
        void get().refreshProject();
      }
    },

    async publishMod(changelog) {
      set({ projectBusy: "publish", publishResult: null, projectError: null });
      try {
        set({ publishResult: await api.projectPublish(changelog) });
      } catch (e) {
        set({ projectError: String(e) });
      } finally {
        set({ projectBusy: null });
      }
    },

    async loadHub() {
      try {
        set({ hub: await api.hubStatus() });
      } catch {
        // The hub row simply stays empty; publishing will report properly.
      }
    },

    async setHubKey(key) {
      try {
        await api.hubSetKey(key);
        set({ hub: await api.hubStatus(), projectError: null });
        return true;
      } catch (e) {
        set({ projectError: String(e) });
        return false;
      }
    },
  };
});
