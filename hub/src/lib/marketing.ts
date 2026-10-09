import type { Metadata } from "next";

export const SITE_URL = "https://mjolnircore.com";
export const DISCORD_URL = "https://discord.gg/9gxYZsByW9";
export const MULTIPLAYER_PATH = "/multiplayer";
export const MULTIPLAYER_RELEASE_PATH = "/blog/classic-multiplayer-alpha";

// Published gameplay captures from the multiplayer alpha announcement.
// Absolute URLs let local previews use the published media, too.
export const MULTIPLAYER_IMAGES = {
  bloodGulch: SITE_URL + "/api/v1/media/85842056-a669-4f26-845f-ade0ed2818cb",
  dangerCanyon: SITE_URL + "/api/v1/media/4a528587-20d4-4503-acc8-73567f30b464",
  chillOut: SITE_URL + "/api/v1/media/0408e37f-635c-42f0-a978-3b74da4965fb",
};

export const MARKETING_DESCRIPTION =
  "Multiplayer modding for Halo Campaign Evolved. Play Slayer and CTF on all 19 classic Halo CE maps, create custom content, and join the MJOLNIR community.";

export function marketingMetadata(title: string, description: string, path: string): Metadata {
  const url = SITE_URL + path;
  const images = [{
    url: MULTIPLAYER_IMAGES.bloodGulch,
    alt: "Blood Gulch in Halo Campaign Evolved with MJOLNIR Core",
  }];
  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: { title, description, url, siteName: "MJOLNIR Core", type: "website", images },
    twitter: { card: "summary_large_image", title, description, images },
  };
}

// Roster from blog/2026-10-02-classic-multiplayer-alpha.md.
export const CLASSIC_MAPS = [
  { name: "Blood Gulch", slug: "ce-blood-gulch" },
  { name: "Battle Creek", slug: "ce-battle-creek" },
  { name: "Sidewinder", slug: "ce-sidewinder" },
  { name: "Damnation", slug: "ce-damnation" },
  { name: "Rat Race", slug: "ce-rat-race" },
  { name: "Prisoner", slug: "ce-prisoner" },
  { name: "Hang 'Em High", slug: "ce-hang-em-high" },
  { name: "Chill Out", slug: "ce-chill-out" },
  { name: "Derelict", slug: "ce-derelict" },
  { name: "Boarding Action", slug: "ce-boarding-action" },
  { name: "Chiron TL-34", slug: "ce-chiron-tl-34" },
  { name: "Longest", slug: "ce-longest" },
  { name: "Wizard", slug: "ce-wizard" },
  { name: "Danger Canyon", slug: "ce-danger-canyon" },
  { name: "Death Island", slug: "ce-death-island" },
  { name: "Gephyrophobia", slug: "ce-gephyrophobia" },
  { name: "Ice Fields", slug: "ce-ice-fields" },
  { name: "Infinity", slug: "ce-infinity" },
  { name: "Timberland", slug: "ce-timberland" },
];

export const PLAY_STEPS = [
  {
    title: "Get the launcher",
    description: "Install MJOLNIR on Windows and set up mods from My Mods. You need your own installed copy of Halo Campaign Evolved.",
  },
  {
    title: "Install multiplayer",
    description: "Open the launcher's Multiplayer page and select Install multiplayer. It installs the classic maps, shared content, and required mods.",
  },
  {
    title: "Bring your fireteam",
    description: "Launch the game, open MULTIPLAYER, choose a map and mode, invite your friends, and start the game. Everyone needs the same maps installed.",
  },
];

// One source for visible answers and the dedicated page's FAQ structured data.
// Keep release limits here until a newer verified release supersedes the alpha.
export const MULTIPLAYER_FAQS = [
  {
    id: "does-campaign-evolved-have-multiplayer",
    question: "Does Halo Campaign Evolved have multiplayer?",
    answer: "Yes — with MJOLNIR Core, you can play classic competitive multiplayer in Halo Campaign Evolved. Our community-made, open-source modding framework adds Slayer and Capture the Flag on all 19 original Halo: Combat Evolved multiplayer maps, including the Halo PC maps. This is a multiplayer mod, separate from the game's official campaign and co-op features, and is currently in alpha.",
    href: MULTIPLAYER_RELEASE_PATH,
    linkLabel: "Read the multiplayer alpha announcement",
  },
  {
    id: "how-to-play",
    question: "How do I play Campaign Evolved multiplayer with friends?",
    answer: "Install the MJOLNIR Launcher, set up mods in My Mods, then open Multiplayer and select Install multiplayer. Launch Halo Campaign Evolved, choose MULTIPLAYER from the main menu, pick a map and game type, invite friends to your fireteam, and start the game. Each player needs their own game installation and the same maps.",
    href: "/download",
    linkLabel: "Download the launcher",
  },
  {
    id: "game-modes",
    question: "Does Campaign Evolved have Slayer, CTF, and other game modes?",
    answer: "MJOLNIR adds Slayer and Capture the Flag to all 19 classic maps. The framework also supports Team Slayer, King of the Hill, and Oddball in its multiplayer menu. A mode is available when both the installed map and its game variant support it; check the map's listing and your in-game mode selector.",
    href: "/maps",
    linkLabel: "Explore maps and supported modes",
  },
  {
    id: "classic-maps",
    question: "Which original Halo CE multiplayer maps can I play?",
    answer: "All 19 classic Halo: Combat Evolved multiplayer maps are available through MJOLNIR, including Blood Gulch, Sidewinder, Battle Creek, Hang 'Em High, and Chill Out, plus Halo PC maps such as Danger Canyon, Death Island, Gephyrophobia, Ice Fields, Infinity, and Timberland. The launcher installs the full classic map collection.",
    href: "/maps",
    linkLabel: "Browse the classic map collection",
  },
  {
    id: "custom-content",
    question: "Can I make custom maps and mods for Campaign Evolved?",
    answer: "Yes. MJOLNIR provides a custom level pipeline, a Blender addon, a tag editor, and command-line tools for authoring maps and changing weapons, textures, and scripts. Creators can package and publish content through the hub. Map creation is an advanced workflow: the current classic-map conversion pipeline needs Unreal Editor and the MJOLNIRMaterials project for cooking, and published map packs go through review.",
    href: "/docs/guides/level-authoring",
    linkLabel: "Start making a custom level",
  },
  {
    id: "player-count",
    question: "How many players can join a multiplayer game?",
    answer: "Up to 16 players, on every classic map. Each player needs their own PC and their own copy of the game, with the same maps installed. More than two players on one PC isn't supported yet.",
    href: MULTIPLAYER_RELEASE_PATH,
    linkLabel: "See the alpha release notes",
  },
  {
    id: "requirements",
    question: "What do I need to play? Does it work with Game Pass?",
    answer: "You need Windows 10 or 11 (64-bit), the MJOLNIR Launcher, and your own copy of Halo Campaign Evolved. The multiplayer alpha is built and tested on Steam. The Xbox app / Game Pass version has not been verified yet. MJOLNIR is free and open source; the base game is a separate requirement.",
    href: "/download",
    linkLabel: "Check downloads and requirements",
  },
  {
    id: "community",
    question: "Where can I find players and get help?",
    answer: "Join the MJOLNIR Discord to find people to play with, get setup help, report alpha issues, and share maps and mods. The hub also has map pages with comments and ratings, creator documentation, and a games page for reported multiplayer lobbies.",
    href: DISCORD_URL,
    linkLabel: "Join the MJOLNIR community",
  },
];
