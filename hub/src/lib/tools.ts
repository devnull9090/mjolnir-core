import { getReleasesFor } from "./changelog";

/**
 * The tools MJOLNIR ships beside the launcher.
 *
 * A tool is a standalone app or command that releases on its own cadence —
 * the same definition `apps/launcher/src-tauri/src/tools.rs` works from. A
 * tool the launcher installs publishes a manifest under
 * `releases.mjolnircore.com/tools/<slug>/latest/`, and the launcher's Tools
 * view reads that to install and update it.
 *
 * This is the registry the site reads: the index, each tool's own page and
 * the sitemap are all generated from it, so adding a tool is one entry here.
 *
 * Kept free of React imports on purpose — the API worker imports it to check
 * that a gallery upload names a tool that exists, and has no business
 * bundling an icon set to do it. `icon` is a key the pages resolve.
 */

/** How you get the tool: a published build, or your own compiler. */
export type ToolAvailability = "download" | "source";

/** Resolved to a component by `app/tools/_components/icons.tsx`. */
export type ToolIcon = "file-code" | "terminal";

export type ToolDownload = {
  label: string;
  /** Absolute URL of the artifact. */
  href: string;
  /** Why you would pick this one over the others. */
  note: string;
};

export type Tool = {
  slug: string;
  name: string;
  /** One line — the card subtitle, and the lead of the page description. */
  tagline: string;
  /** Two or three sentences, for the top of the tool's own page. */
  summary: string;
  availability: ToolAvailability;
  icon: ToolIcon;
  /** Product id in `changelog/products.json`, when the tool cuts releases. */
  changelogProduct?: string;
  docsUrl?: string;
  repoUrl: string;
  /** What the tool does. The card shows the first three. */
  highlights: { title: string; body: string }[];
  requirements: { label: string; value: string }[];
  /** Published artifacts. Empty for a tool you build yourself. */
  downloads: ToolDownload[];
  /** How to build it, for a tool that ships no binary. */
  build?: { intro: string; steps: { label: string; command: string }[] };
  /**
   * Root of the tool's release directory, when the launcher installs it.
   * `latest/manifest.json` under here is what `/api/tools/latest` reads.
   */
  releaseBase?: string;
};

export const TOOLS: Tool[] = [
  {
    slug: "tag-editor",
    name: "MJOLNIR Tag Editor",
    tagline: "Browse and edit the Blam tags, textures and audio inside your installed game.",
    summary:
      "A desktop editor for the game's own data. It reads the installed containers directly — no extraction step, nothing shipped is ever modified — and turns them into something you can search, read and change. Edits become a mod project you can test in the running game and publish to the hub.",
    availability: "download",
    icon: "file-code",
    changelogProduct: "tag-editor",
    docsUrl: "/docs/guides/tag-editing-guide",
    repoUrl: "https://github.com/devnull9090/mjolnir-core/tree/main/apps/tag-editor",
    highlights: [
      {
        title: "Every asset, four ways in",
        body: "Browse by file path or by Blam group, or narrow straight to the textures or the audio. Search spans all 101 groups at once, and anything you open gets a tab of its own.",
      },
      {
        title: "Values you can trust",
        body: "Each tag says whether its field walk consumed the whole payload — values exact or values partial. A tag that cannot be read names the field the walk stopped at instead of guessing.",
      },
      {
        title: "Edits that verify themselves",
        body: "An edit is applied to a copy, re-parsed from scratch and read back before it is recorded. A value that does not fit is refused and the field is left alone, with the reason shown.",
      },
      {
        title: "Mod projects, not loose files",
        body: "Edits autosave into a project as a recipe of what changed. From there: test in game as an override container, export a .mjolnir archive, or publish straight to the hub.",
      },
      {
        title: "Textures and audio",
        body: "4,787 of the install's 4,844 textures decode and export as PNG. The Wwise banks play in place, named by the event that fires them rather than by a numeric id.",
      },
      {
        title: "Live mode",
        body: "Write a value into the running game and see it immediately — no bake, no restart, nothing touched on disk. Verified end to end: jump velocity 9.0 → 25.0 took a jump arc from 3,005 cm to 11,618 cm.",
      },
    ],
    requirements: [
      { label: "OS", value: "Windows 10/11 (64-bit)" },
      { label: "Runtime", value: "WebView2 (included in Win 11)" },
      { label: "Game", value: "Halo Campaign Evolved (Steam)" },
      { label: "Oodle", value: "Optional — a decoder is built in" },
    ],
    downloads: [
      {
        label: "Portable (.exe)",
        href: "https://releases.mjolnircore.com/tools/tag-editor/latest/mjolnir-tag-editor.exe",
        note: "No installer, no UAC prompt. This is the build the launcher installs.",
      },
      {
        label: "Installer (.msi)",
        href: "https://releases.mjolnircore.com/tools/tag-editor/latest/MJOLNIR-Tag-Editor-latest.msi",
        note: "Start-menu entry and an uninstaller.",
      },
      {
        label: "Setup (.exe)",
        href: "https://releases.mjolnircore.com/tools/tag-editor/latest/MJOLNIR-Tag-Editor-latest-setup.exe",
        note: "NSIS installer, if you prefer it to the MSI.",
      },
    ],
    releaseBase: "https://releases.mjolnircore.com/tools/tag-editor",
  },
  {
    slug: "mjolnir-cli",
    name: "mjolnir CLI",
    tagline: "Inspect and patch tag data from the command line.",
    summary:
      "The same tag engine the editor runs on, driven from a shell. It reads an installed game read-only, prints fields with their resolved values, and patches one by name — as a dry run until you ask for a file. It is also how the format's claims are checked, over all 12,290 shipped tags at once.",
    availability: "source",
    icon: "terminal",
    docsUrl: "/docs/guides/tag-editing-guide",
    repoUrl: "https://github.com/devnull9090/mjolnir-core/tree/main/crates/blam-cli",
    highlights: [
      {
        title: "Find your way around",
        body: "mjolnir groups summarises all 101 tag groups with counts; mjolnir list and mjolnir values take you from a group to one tag's fields, with enums, bitfields, references and colours resolved to names.",
      },
      {
        title: "Set a field by path",
        body: "The same dotted path the editor shows on hover. Every set reports which bytes moved, re-parses the result and reads the value back out — and writes nothing until you pass --out.",
      },
      {
        title: "Check the whole install",
        body: "validate, roundtrip and recode run over all 12,290 tags: structural invariants, byte-identical rewrites, and a decode/re-encode of every field. None of them writes anything.",
      },
      {
        title: "Poke the running game",
        body: "mjolnir poke locates a tag's payload in the live process and writes a field into it, confirming the bytes afterwards. Gone at the next launch, and never on disk.",
      },
      {
        title: "Export the schema",
        body: "mjolnir defs dumps the whole definition corpus as JSON — field names, types and offsets. Schema only: extracted tag values are game content and stay on your machine.",
      },
    ],
    requirements: [
      { label: "Toolchain", value: "Rust (stable) — cargo build" },
      { label: "Game", value: "Halo Campaign Evolved (Steam)" },
      { label: "Paths", value: "HCE_PAKS env var, or --paks" },
      { label: "Oodle", value: "Optional — OODLE points at a DLL for ~4× faster decodes" },
    ],
    downloads: [],
    build: {
      intro:
        "No binary is published yet — build it from the repository. The result lands at target/release/mjolnir.",
      steps: [
        { label: "Clone", command: "git clone https://github.com/devnull9090/mjolnir-core" },
        { label: "Build", command: "cd mjolnir-core; cargo build --release -p blam-cli" },
        {
          label: "Point it at the game",
          command:
            '$env:HCE_PAKS = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Halo Campaign Evolved\\Meteorite\\Content\\Paks"',
        },
        { label: "Try it", command: ".\\target\\release\\mjolnir.exe groups" },
      ],
    },
  },
];

/**
 * What `/api/tools/latest` reports for one tool, read from the release
 * manifest the launcher installs from.
 */
export type ToolRelease = {
  id: string;
  version: string | null;
  exe: string | null;
  url: string | null;
  sha256: string | null;
  size: number | null;
  checksums_url: string;
  /** Why the manifest could not be read, when it could not be. */
  error: string | null;
};

export function getTool(slug: string): Tool | null {
  return TOOLS.find((tool) => tool.slug === slug) ?? null;
}

/**
 * The tool's newest published version, from the changelog it already keeps.
 *
 * Read from local data rather than from the release manifest, so a page still
 * names a version when the CDN is unreachable. The live manifest — with the
 * hash and the download size — is layered on top of this in the browser by
 * `ToolRelease`, against `/api/tools/latest`.
 */
export function getToolVersion(tool: Tool): string | null {
  if (!tool.changelogProduct) return null;
  return getReleasesFor(tool.changelogProduct)[0]?.version ?? null;
}

/** Tools whose builds the launcher can install, in registry order. */
export function getInstallableTools(): Tool[] {
  return TOOLS.filter((tool) => !!tool.releaseBase);
}
