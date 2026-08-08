import { create } from "zustand";
import {
  api,
  type DirEntry,
  type EditResult,
  type ExportView,
  type GroupSummary,
  type HubStatus,
  type LinkStart,
  type LinkedAsset,
  type LiveStatus,
  type ProjectView,
  type PublishView,
  type SigningStatus,
  type SoundSummary,
  type SoundView,
  type TagSummary,
  type TagView,
  type TestView,
  type TextureSummary,
  type TextureView,
  type SwapReport,
  type ScriptView,
  type CompileReport,
} from "../lib/api";

type Status = "idle" | "detecting" | "opening" | "ready" | "error";

export type ViewMode = "form" | "tree" | "script" | "model" | "world";

/** Groups whose geometry the Model view can draw. */
export const MODEL_GROUPS = ["model", "collision_model", "skeleton_model"];

/** One open document: a tag, a texture, a sound or a mesh, shown as a tab. */
export type Tab = {
  id: number;
  kind: "tag" | "texture" | "sound" | "mesh";
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
  /** True once an installation has opened, so the setup form knows it is a
   *  change of mind rather than a first run and can be backed out of. */
  opened: boolean;

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
  /** Mesh catalog index shown by the active mesh tab, if any. */
  selectedMesh: number | null;
  tag: TagView | null;
  tagLoading: boolean;
  /** Packages the current tag imports, resolved to openable things. */
  tagLinks: LinkedAsset[];
  /** The last edit applied, so the UI can confirm what it did. */
  lastEdit: EditResult | null;
  editError: string | null;

  /**
   * Live mode: mirror every accepted edit into the running game as well as the
   * project, so a number can be tuned without a bake and a restart.
   *
   * Off by default and never implied. It writes into another process's memory,
   * which is a thing to opt into deliberately rather than inherit from a
   * previous session.
   */
  live: LiveStatus | null;
  liveOn: boolean;
  /** Set while a poke is in flight; the first one for a tag takes minutes. */
  livePoking: boolean;
  /** What the last poke did, or why it could not. */
  liveNote: string | null;
  refreshLive: () => Promise<void>;
  setLiveOn: (on: boolean) => void;

  /** How the inspector renders: Guerilla-style form or a flat field tree. */
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;

  /** What the left panel browses: assets, tag groups, textures, sounds, or
   * the mod. */
  browse: "files" | "tags" | "textures" | "sounds" | "mod";
  setBrowse: (browse: "files" | "tags" | "textures" | "sounds" | "mod") => void;

  /** The open mod project; edits autosave into it while one is open. */
  project: ProjectView | null;
  projectError: string | null;
  /** Which long-running mod action is in flight, to disable its button. */
  projectBusy: "export" | "test" | "untest" | "publish" | null;
  exportResult: ExportView | null;
  testResult: TestView | null;
  publishResult: PublishView | null;
  hub: HubStatus | null;
  /** This device's signing key, shown in the publish section. */
  signing: SigningStatus | null;
  loadSigning: () => Promise<void>;
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
  /** A link waiting on the browser, with how it ended if it did. */
  link: (LinkStart & { status: "pending" | "denied" | "expired" }) | null;
  /**
   * Start linking. Returns the page to open so the caller can send the user
   * there; polling continues in the background until it resolves, the code
   * expires, or `cancelHubLink` is called.
   */
  startHubLink: () => Promise<LinkStart | null>;
  cancelHubLink: () => void;
  unlinkHub: () => Promise<void>;

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
  /** Set while a swap is re-encoding, which takes seconds on a large texture. */
  textureSwapping: boolean;
  /** What the last applied swap did, cleared when another texture is opened. */
  swapReport: SwapReport | null;
  swapTexture: (image: string) => Promise<void>;
  revertTexture: () => Promise<void>;

  /** The open scenario's Blam script, loaded on demand. */
  scripts: ScriptView | null;
  scriptsLoading: boolean;
  scriptsError: string | null;
  /** Which source file the script view is showing. */
  scriptFile: string | null;
  loadScripts: () => Promise<void>;
  setScriptFile: (name: string) => void;
  exportScript: (dest: string, name: string) => Promise<number | null>;

  /** Source the user has changed but not applied, by file name. */
  scriptDrafts: Record<string, string>;
  /** What the last compile said. Null before one has run. */
  scriptReport: CompileReport | null;
  scriptCompiling: boolean;
  /** Whether this scenario's script is part of the mod. */
  scriptApplied: boolean;
  editScript: (name: string, text: string) => void;
  compileScripts: () => Promise<void>;
  applyScripts: () => Promise<boolean>;
  revertScripts: () => Promise<void>;
  discardScriptDrafts: () => void;
  sounds: SoundSummary[];
  soundQuery: string;
  /** A listing is in flight; an empty list means "not yet", not "none". */
  soundsLoading: boolean;
  searchSounds: (query: string) => Promise<void>;
  selectedSound: number | null;
  sound: SoundView | null;
  soundLoading: boolean;
  soundError: string | null;
  exportSound: (dest: string) => Promise<number | null>;

  detect: () => Promise<void>;
  open: (paks: string, oodle: string) => Promise<void>;
  /** Show the setup form again, to point the editor at another installation. */
  changeInstall: () => void;
  /** Back out of that, leaving the open installation as it was. */
  cancelChange: () => void;
  selectGroup: (group: string) => Promise<void>;
  search: (query: string) => Promise<void>;
  setField: (path: string, value: string) => Promise<boolean>;
  /** Open the tag a reference points at, given its four-CC and Blam path. */
  followReference: (fourCc: string, path: string) => Promise<boolean>;
  pokeLive: (index: number, path: string, value: string) => Promise<void>;
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

/** The catalog index of the tag in the active tab, if there is one. */
function activeTagIndex(s: EditorState): number | null {
  const tab = s.tabs.find((t) => t.id === s.activeTab);
  return tab && tab.kind === "tag" ? tab.index : null;
}

/**
 * Every source file as it currently stands, drafts applied.
 *
 * The decompiled fallback is left out: it is a rendering of the tree, not
 * source the scenario carries, and compiling it back in would silently make it
 * the mod's source of truth.
 */
function scriptFilesFor(s: EditorState): [string, string][] {
  const files = s.scripts?.source_files ?? [];
  return files
    .filter((f) => !f.name.startsWith("<"))
    .map((f) => [f.name, s.scriptDrafts[f.name] ?? f.text] as [string, string]);
}

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
      // The note belongs to the tag that was open; the toggle does not.
      liveNote: null,
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
    // The report describes one swap of one texture, so it does not survive
    // moving to another.
    set({
      selectedTexture: index,
      selectedTag: null,
      textureError: null,
      swapReport: null,
    });
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

  /** Load a sound's header into the active-content slots. */
  async function loadSound(index: number) {
    set({
      selectedSound: index,
      selectedTag: null,
      selectedTexture: null,
      soundError: null,
      soundLoading: true,
      sound: null,
    });
    try {
      const sound = await api.readSound(index);
      // Only show it if this tab is still the active one.
      if (get().selectedSound === index) set({ sound, soundLoading: false });
    } catch (e) {
      if (get().selectedSound === index) {
        set({ soundError: String(e), soundLoading: false });
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
    opened: false,

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
      } else if (tab.kind === "sound") {
        await loadSound(tab.index);
      } else if (tab.kind === "mesh") {
        // The mesh viewer loads its own payload; just mark the selection.
        set({
          selectedMesh: tab.index,
          selectedTag: null,
          selectedTexture: null,
          selectedSound: null,
        });
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
          selectedSound: null,
          sound: null,
          soundError: null,
          lastEdit: null,
          editError: null,
        });
      }
    },

    selectedTag: null,
    selectedMesh: null,
    tag: null,
    tagLoading: false,
    tagLinks: [],
    lastEdit: null,
    editError: null,

    // Off on every launch, on purpose: writing into another process is opted
    // into per session rather than inherited from the last one.
    live: null,
    liveOn: false,
    livePoking: false,
    liveNote: null,

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
      if (browse === "sounds" && get().sounds.length === 0) {
        void get().searchSounds("");
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
    textureSwapping: false,
    swapReport: null,
    async swapTexture(image) {
      const index = get().selectedTexture;
      if (index === null) return;
      set({ textureSwapping: true, swapReport: null, textureError: null });
      try {
        const report = await api.swapTexture(index, image);
        // The cached view still holds the shipped image, so it has to go or
        // reopening the tab would show the texture as it was.
        textureCache.delete(index);
        const texture = await api.readTexture(index);
        textureCache.set(index, texture);
        if (get().selectedTexture === index) set({ texture, swapReport: report });
      } catch (e) {
        set({ textureError: String(e) });
      } finally {
        set({ textureSwapping: false });
        if (get().project) void get().refreshProject();
      }
    },
    async revertTexture() {
      const index = get().selectedTexture;
      if (index === null) return;
      set({ textureError: null });
      try {
        await api.revertTexture(index);
        textureCache.delete(index);
        const texture = await api.readTexture(index);
        textureCache.set(index, texture);
        if (get().selectedTexture === index) set({ texture, swapReport: null });
      } catch (e) {
        set({ textureError: String(e) });
      } finally {
        if (get().project) void get().refreshProject();
      }
    },
    scripts: null,
    scriptsLoading: false,
    scriptsError: null,
    scriptFile: null,

    /**
     * Load the open tag's script section.
     *
     * Only scenarios have one, and a scenario is the largest tag the game
     * ships, so this is on demand rather than part of `loadTag`.
     */
    async loadScripts() {
      const { tabs, activeTab } = get();
      const tab = tabs.find((t) => t.id === activeTab);
      if (!tab || tab.kind !== "tag") return;
      const index = tab.index;
      set({ scriptsLoading: true, scriptsError: null, scripts: null });
      try {
        const scripts = await api.readScripts(index);
        // The tab can change while a twelve-megabyte scenario is being read.
        const current = get().tabs.find((t) => t.id === get().activeTab);
        if (current?.index !== index) return;
        set({
          scripts,
          scriptsLoading: false,
          scriptFile: scripts.source_files[0]?.name ?? null,
        });
      } catch (e) {
        set({ scriptsError: String(e), scriptsLoading: false });
      }
    },

    setScriptFile(name) {
      set({ scriptFile: name });
    },

    scriptDrafts: {},
    scriptReport: null,
    scriptCompiling: false,
    scriptApplied: false,

    editScript(name, text) {
      set((s) => ({ scriptDrafts: { ...s.scriptDrafts, [name]: text } }));
    },

    discardScriptDrafts() {
      set({ scriptDrafts: {}, scriptReport: null });
    },

    /**
     * Compile what is on screen without recording anything.
     *
     * Sends every file, not just the edited one: a script may call one declared
     * in another file, so compiling a single file in isolation would report
     * every cross-file call as an unknown name.
     */
    async compileScripts() {
      const index = activeTagIndex(get());
      if (index === null) return;
      const files = scriptFilesFor(get());
      if (files.length === 0) return;
      set({ scriptCompiling: true });
      try {
        const report = await api.compileScripts(index, files);
        if (activeTagIndex(get()) === index) set({ scriptReport: report });
      } catch (e) {
        set({ scriptsError: String(e) });
      } finally {
        set({ scriptCompiling: false });
      }
    },

    async applyScripts() {
      const index = activeTagIndex(get());
      if (index === null) return false;
      const files = scriptFilesFor(get());
      set({ scriptCompiling: true, scriptsError: null });
      try {
        const report = await api.setScripts(index, files);
        set({ scriptReport: report });
        if (!report.ok) return false;
        // The drafts are now what the tag holds, so re-reading is what keeps
        // the outline and the decompiled view honest.
        set((s) => ({
          scriptDrafts: {},
          scriptApplied: true,
          dirtyTags: { ...s.dirtyTags, [index]: true },
        }));
        await get().loadScripts();
        await get().refreshProject();
        return true;
      } catch (e) {
        set({ scriptsError: String(e) });
        return false;
      } finally {
        set({ scriptCompiling: false });
      }
    },

    async revertScripts() {
      const index = activeTagIndex(get());
      if (index === null) return;
      try {
        await api.revertScripts(index);
        set({ scriptDrafts: {}, scriptReport: null, scriptApplied: false });
        await get().loadScripts();
        await get().refreshProject();
      } catch (e) {
        set({ scriptsError: String(e) });
      }
    },

    async exportScript(dest, name) {
      const { tabs, activeTab } = get();
      const tab = tabs.find((t) => t.id === activeTab);
      if (!tab || tab.kind !== "tag") return null;
      try {
        return await api.exportScript(tab.index, name, dest);
      } catch (e) {
        set({ scriptsError: String(e) });
        return null;
      }
    },

    sounds: [],
    soundQuery: "",
    soundsLoading: false,
    async searchSounds(query) {
      // The first listing also builds the Wwise name index, which reads every
      // cooked audio package and takes seconds — long enough that an empty
      // list reads as "no sounds" unless the wait is shown.
      set({ soundQuery: query, soundsLoading: true });
      try {
        set({ sounds: await api.listSounds(query) });
      } catch (e) {
        set({ error: String(e) });
      } finally {
        set({ soundsLoading: false });
      }
    },
    selectedSound: null,
    sound: null,
    soundLoading: false,
    soundError: null,
    async exportSound(dest) {
      const index = get().selectedSound;
      if (index === null) return null;
      try {
        return await api.exportSound(index, dest);
      } catch (e) {
        set({ soundError: String(e) });
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

    changeInstall() {
      set({ status: "idle", error: null });
    },

    cancelChange() {
      // Only meaningful with something open behind the form; otherwise there
      // is nothing to go back to.
      if (get().opened) set({ status: "ready", error: null });
    },

    async open(paks, oodle) {
      set({ status: "opening", error: null });
      try {
        // The backend accepts anything that names the installation and
        // answers with the folder it actually opened, which is what the rest
        // of the UI should show.
        const opened = await api.openInstall(paks, oodle);
        paks = opened.paks;
        const groups = await api.listGroups();
        // `dirLoading` goes up with the shell so the file list shows its
        // spinner instead of "Empty." for the frame before the root arrives.
        set({
          status: "ready",
          groups,
          paks,
          oodle,
          note: null,
          opened: true,
          dirLoading: true,
        });
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

    async refreshLive() {
      try {
        set({ live: await api.liveStatus() });
      } catch {
        // Not being able to see the game is a normal state, not an error worth
        // putting in front of the user.
        set({ live: null });
      }
    },

    setLiveOn(on) {
      set({ liveOn: on, liveNote: null });
      if (on) void get().refreshLive();
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
        // The project is the record of what the edit is; the poke only makes it
        // visible now. So it happens after the edit is safely recorded, and a
        // failure to reach the game never fails the edit.
        if (get().liveOn && index !== null) void get().pokeLive(index, path, value);
        return true;
      } catch (e) {
        set({ editError: String(e), lastEdit: null });
        return false;
      }
    },

    async pokeLive(index, path, value) {
      set({ livePoking: true, liveNote: null });
      try {
        const poked = await api.livePoke(index, path, value);
        set({
          livePoking: false,
          liveNote: poked.scanned
            ? `live: found the tag at ${poked.base} and set ${path}`
            : `live: set ${path}`,
        });
        void get().refreshLive();
      } catch (e) {
        set({ livePoking: false, liveNote: `live: ${String(e)}` });
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
        // Publishing creates and registers the device key on first run.
        void get().loadSigning();
      }
    },

    signing: null,
    async loadSigning() {
      try {
        set({ signing: await api.signingStatus() });
      } catch {
        // The signing line simply stays empty.
      }
    },

    async loadHub() {
      try {
        set({ hub: await api.hubStatus() });
      } catch {
        // The hub row simply stays empty; publishing will report properly.
      }
      void get().loadSigning();
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

    link: null,

    async startHubLink() {
      let started: LinkStart;
      try {
        started = await api.hubLinkStart();
      } catch (e) {
        set({ projectError: String(e) });
        return null;
      }
      set({ link: { ...started, status: "pending" }, projectError: null });

      // Polling runs detached: the caller opens the browser and the panel
      // shows the code while this waits. Every step re-reads `link` and stops
      // if the code on screen is no longer this one, which is what makes
      // cancelling — or starting over — actually end the previous loop.
      const mine = () => get().link?.user_code === started.user_code;
      const deadline = Date.now() + started.expires_in * 1000;
      const wait = Math.max(1, started.interval) * 1000;
      void (async () => {
        while (mine()) {
          await new Promise((resolve) => setTimeout(resolve, wait));
          if (!mine()) return;
          try {
            const polled = await api.hubLinkPoll();
            if (polled.status === "approved") {
              set({ link: null });
              await get().loadHub();
              return;
            }
            if (polled.status !== "pending") {
              set({ link: { ...started, status: polled.status as "denied" | "expired" } });
              return;
            }
          } catch (e) {
            set({ link: null, projectError: String(e) });
            return;
          }
          // The hub expires the code on its own schedule; this only stops the
          // editor from polling a code it knows is dead.
          if (Date.now() > deadline) {
            set({ link: { ...started, status: "expired" } });
            return;
          }
        }
      })();

      return started;
    },

    cancelHubLink() {
      set({ link: null });
    },

    async unlinkHub() {
      try {
        await api.hubUnlink();
        set({ link: null, projectError: null });
        await get().loadHub();
      } catch (e) {
        set({ projectError: String(e) });
      }
    },
  };
});
