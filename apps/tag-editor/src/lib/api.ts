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

export type ScriptSourceFile = {
  name: string;
  text: string;
  lines: number;
  bytes: number;
  flags: string[];
};

export type ScriptDecl = {
  name: string;
  kind: string;
  return_type: string;
  parameters: string[];
  file: string | null;
  line: number | null;
};

export type GlobalDecl = {
  name: string;
  value_type: string;
  initializer: string;
  file: string | null;
  line: number | null;
};

export type ScriptView = {
  path: string;
  source_files: ScriptSourceFile[];
  scripts: ScriptDecl[];
  globals: GlobalDecl[];
  references: string[];
  expressions: number;
  datum_slots: number;
  string_bytes: number;
  /** False when the tag shipped no source and the text shown is decompiled. */
  has_source: boolean;
  /** Whether the mod replaces this scenario's script. */
  edited: boolean;
};

export type ScriptDiagnostic = {
  line: number;
  message: string;
};

export type CompileReport = {
  ok: boolean;
  errors: ScriptDiagnostic[];
  warnings: ScriptDiagnostic[];
  scripts: number;
  globals: number;
  expressions: number;
  tag_bytes: number;
  original_bytes: number;
  /** Scripts the tag has that this source does not declare; rebuilding drops them. */
  dropped: string[];
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
  /** Why this format cannot be swapped, or null when Replace is available. */
  unsupported: string | null;
  /** Whether the open mod replaces this texture; png is then the replacement. */
  replaced: boolean;
};

/** What a swap did, reported once, when it is applied. */
export type SwapReport = {
  mips: number;
  changed: number;
  payload: number;
  /** Mean per-channel readback error out of 255. */
  error: number;
  /** The rewritten payload decoded again — what the game will show. */
  png: string;
};

export type SoundSummary = {
  index: number;
  path: string;
  /** Language folder, or null for audio shared across languages. */
  language: string | null;
  size: number;
  /** The Wwise event that plays this, when one claims it; Wwise names media numerically. */
  event: string | null;
};

/** A playable stream built from one .wem. */
export type SoundAudio = {
  /** Data URI, ready for an audio element. */
  src: string;
  /** How it was produced, e.g. which codebook library. */
  via: string;
  bytes: number;
};

/** One Wwise event that plays a media file. */
export type EventRef = {
  name: string;
  package: string;
  /** The authored .wav files the event draws from, as a set. */
  sources: string[];
};

/** What a `.wem` header says about its audio. */
export type WemInfo = {
  codec: string;
  format_tag: number;
  channels: number;
  sample_rate: number;
  avg_bytes_per_sec: number;
  /** Decoded length in samples per channel, when the header records it. */
  sample_count: number | null;
  duration_secs: number | null;
  data_size: number;
  chunks: string[];
};

export type SoundView = {
  path: string;
  language: string | null;
  size: number;
  /** Absent for a sound bank, or when the header could not be read. */
  info: WemInfo | null;
  error: string | null;
  /** Every Wwise event that plays this media. */
  events: EventRef[];
};

/** One row of the virtual asset filesystem: a folder or an openable asset. */
export type DirEntry = {
  name: string;
  path: string;
  kind: "dir" | "tag" | "texture" | "sound";
  /** Catalog index, for files only. */
  index: number | null;
  size: number;
  /** Assets beneath a folder, at any depth. */
  children: number | null;
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

export type ProjectMeta = {
  schema_version: number;
  name: string;
  slug: string;
  version: string;
  summary: string;
};

/** One edited field in the project change list. */
export type FieldChange = {
  field: string;
  /** The value the mod sets, as typed. */
  value: string;
  /** The shipped value, when the field still resolves. */
  before: string | null;
  /** The tag or field no longer resolves — usually a game update. */
  stale: boolean;
};

/** Every edit the project makes to one tag. */
export type TagChange = {
  group: string;
  tag: string;
  /** Catalog index in the open installation, when the tag still exists. */
  index: number | null;
  edits: FieldChange[];
};

/** One texture the project repaints. */
export type TextureChange = {
  path: string;
  /** Catalog index in the open installation, when the texture still exists. */
  index: number | null;
  /** Size of the replacement image the recipe holds. */
  bytes: number;
};

export type ProjectView = {
  root: string;
  meta: ProjectMeta;
  changes: TagChange[];
  textures: TextureChange[];
  /** Files a test install left in the Paks folder. */
  test_files: string[];
};

export type ExportView = {
  archive: string;
  size: number;
  containers: string[];
  chunk_count: number;
  resized: boolean;
  /** The archive carries an author signature from this device's key. */
  signed: boolean;
  signer_fingerprint: string | null;
  warnings: string[];
};

export type SigningStatus = {
  /** This device's key fingerprint; null until a key is first created. */
  fingerprint: string | null;
  /** Registered to the hub account; null when unknown (no key/API key). */
  registered: boolean | null;
  /** The label registration uses — the machine name. */
  label: string;
};

export type TestView = {
  files: string[];
  resized: boolean;
  warnings: string[];
};

/** One scanner finding, verbatim from the hub. */
export type Finding = {
  level: string;
  code: string;
  message: string;
};

export type PublishView = {
  slug: string;
  version: string;
  /** `published`, or `rejected` with the findings saying why. */
  status: string;
  findings: Finding[];
  url: string;
};

export type HubStatus = {
  base: string;
  has_key: boolean;
  /** Who the stored key belongs to, when the editor knows. */
  username: string | null;
};

/** A link waiting to be approved: what to show, and where to send them. */
export type LinkStart = {
  user_code: string;
  verification_url: string;
  /** Seconds between polls, as the hub asked. */
  interval: number;
  expires_in: number;
};

/** `pending`, `approved`, `denied` or `expired`. */
export type LinkPoll = {
  status: string;
  username: string | null;
};

/** Whether a game is running to push edits into, and what we know about it. */
export type LiveStatus = {
  running: boolean;
  pid: number | null;
  /** Tags whose address is already known, so an edit to them is instant. */
  located: number;
};

/** The result of pushing one field into the running game. */
export type Poked = {
  /** The field's bytes in the game before this write, as hex. */
  was: string;
  now: string;
  /** True when the tag had to be found first, which takes minutes. */
  scanned: boolean;
  base: string;
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
  liveStatus: () => invoke<LiveStatus>("live_status"),
  liveForget: () => invoke<void>("live_forget"),
  livePoke: (index: number, path: string, value: string) =>
    invoke<Poked>("live_poke", { index, path, value }),
  revertField: (index: number, path: string) =>
    invoke<number>("revert_field", { index, path }),
  revertTag: (index: number) => invoke<void>("revert_tag", { index }),
  exportTag: (index: number, dest: string) =>
    invoke<number>("export_tag", { index, dest }),
  listTextures: (query: string) =>
    invoke<TextureSummary[]>("list_textures", { query }),
  readTexture: (index: number) => invoke<TextureView>("read_texture", { index }),
  readScripts: (index: number) => invoke<ScriptView>("read_scripts", { index }),
  decompileScript: (index: number, name: string) =>
    invoke<string>("decompile_script", { index, name }),
  exportScript: (index: number, name: string, dest: string) =>
    invoke<number>("export_script", { index, name, dest }),
  compileScripts: (index: number, files: [string, string][]) =>
    invoke<CompileReport>("compile_scripts", { index, files }),
  setScripts: (index: number, files: [string, string][]) =>
    invoke<CompileReport>("set_scripts", { index, files }),
  revertScripts: (index: number) => invoke<void>("revert_scripts", { index }),
  exportTexture: (index: number, dest: string) =>
    invoke<number>("export_texture", { index, dest }),
  swapTexture: (index: number, image: string) =>
    invoke<SwapReport>("swap_texture", { index, image }),
  revertTexture: (index: number) => invoke<void>("revert_texture", { index }),
  listSounds: (query: string) => invoke<SoundSummary[]>("list_sounds", { query }),
  playSound: (index: number) => invoke<SoundAudio>("play_sound", { index }),
  readSound: (index: number) => invoke<SoundView>("read_sound", { index }),
  exportSound: (index: number, dest: string) =>
    invoke<number>("export_sound", { index, dest }),
  tagLinks: (index: number) => invoke<LinkedAsset[]>("tag_links", { index }),
  listDir: (path: string) => invoke<DirEntry[]>("list_dir", { path }),
  searchFiles: (query: string) => invoke<DirEntry[]>("search_files", { query }),
  projectStatus: () => invoke<ProjectView | null>("project_status"),
  projectNew: (dir: string, name: string, slug: string, version: string, summary: string) =>
    invoke<ProjectView>("project_new", { dir, name, slug, version, summary }),
  projectOpen: (dir: string) => invoke<ProjectView>("project_open", { dir }),
  projectClose: () => invoke<void>("project_close"),
  projectSetMeta: (name: string, slug: string, version: string, summary: string) =>
    invoke<ProjectView>("project_set_meta", { name, slug, version, summary }),
  projectRevert: (group: string, tag: string, field: string | null) =>
    invoke<void>("project_revert", { group, tag, field }),
  lastProject: () => invoke<string | null>("last_project"),
  projectExport: () => invoke<ExportView>("project_export"),
  projectTest: () => invoke<TestView>("project_test"),
  projectUntest: () => invoke<number>("project_untest"),
  projectPublish: (changelog: string) =>
    invoke<PublishView>("project_publish", { changelog }),
  hubStatus: () => invoke<HubStatus>("hub_status"),
  hubSetKey: (key: string) => invoke<void>("hub_set_key", { key }),
  hubLinkStart: () => invoke<LinkStart>("hub_link_start"),
  hubLinkPoll: () => invoke<LinkPoll>("hub_link_poll"),
  hubUnlink: () => invoke<void>("hub_unlink"),
  signingStatus: () => invoke<SigningStatus>("signing_status"),
};

export type Api = typeof tauriApi;

/**
 * Outside Tauri (plain `vite dev`) the IPC bridge does not exist, so a mock
 * with sample data stands in and the interface can be reviewed in a browser.
 */
export const api: Api = isTauri ? tauriApi : (mockApi as unknown as Api);
