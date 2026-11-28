import type { Metadata } from "next";

export const SITE_URL = "https://mjolnircore.com";
export const DISCORD_URL = "https://discord.gg/9gxYZsByW9";
export const MULTIPLAYER_PATH = "/multiplayer";
export const MULTIPLAYER_RELEASE_PATH = "/blog/classic-multiplayer-alpha";

// Published gameplay captures from the multiplayer alpha announcement.
// Absolute URLs let local previews use the published media, too.
export const MULTIPLAYER_IMAGES = {
  bloodGulch: SITE_URL + "/api/v1/media/a5f46d72-16af-4e0e-866d-226645d19df1",
  dangerCanyon: SITE_URL + "/api/v1/media/4a528587-20d4-4503-acc8-73567f30b464",
  chillOut: SITE_URL + "/api/v1/media/0408e37f-635c-42f0-a978-3b74da4965fb",
  sidewinder: SITE_URL + "/api/v1/media/bb355829-2256-4ca3-9d62-54d2d28e4dc9",
  deathIsland: SITE_URL + "/api/v1/media/f6094fab-cd72-45dd-9678-917ae93a2fdd",
  timberland: SITE_URL + "/api/v1/media/51aa12e4-88fb-4771-9f72-b33ff9cd3669",
  gephyrophobia: SITE_URL + "/api/v1/media/3c4dbc54-7867-4f5c-9ef0-bfbe45432e20",
  battleCreek: SITE_URL + "/api/v1/media/99f90742-0704-4005-b5f6-6eb7c91dc473",
  hangEmHigh: SITE_URL + "/api/v1/media/6adbdf7d-cd36-4527-803b-b66c39ad59e4",
  iceFields: SITE_URL + "/api/v1/media/a8cb0d75-4757-497e-acba-a002acc6a1df",
  infinity: SITE_URL + "/api/v1/media/273a8f9d-21d3-4b5f-9c49-b3943e782126",
  damnation: SITE_URL + "/api/v1/media/d727ce9f-d824-4abd-a4d7-126a94e57873",
  prisoner: SITE_URL + "/api/v1/media/56052ddc-f17c-44fd-b3b1-1cca71a1e884",
  ratRace: SITE_URL + "/api/v1/media/48f8eb14-aac0-4752-9cfd-c6096a5836e4",
  longest: SITE_URL + "/api/v1/media/53d7cd4f-825c-4665-909f-9dbf257ada2e",
  wizard: SITE_URL + "/api/v1/media/69855ffd-4584-4b8f-8f33-573926c3d3da",
  derelict: SITE_URL + "/api/v1/media/0be2dd28-e87e-443f-ae9e-0ebae8d8cb28",
  boardingAction: SITE_URL + "/api/v1/media/3ae0fad0-8894-4ab6-821d-88bca070fc6a",
  chiron: SITE_URL + "/api/v1/media/404c4e00-cbae-4004-a220-f4c15ff70375",
};

export interface HeroScene {
  name: string;
  code: string;
  slug: string;
  image: string;
  alt: string;
  /** CSS object-position tuning for widescreen framing. */
  position?: string;
}

/** Curated scenic captures rotated across the homepage hero backdrop. */
export const HERO_SCENES: HeroScene[] = [
  {
    name: "Blood Gulch",
    code: "BGL",
    slug: "ce-blood-gulch",
    image: MULTIPLAYER_IMAGES.bloodGulch,
    alt: "Blood Gulch canyon and bases rebuilt inside Halo Campaign Evolved",
    position: "center 45%",
  },
  {
    name: "Sidewinder",
    code: "SDW",
    slug: "ce-sidewinder",
    image: MULTIPLAYER_IMAGES.sidewinder,
    alt: "Snowy horseshoe canyon of Sidewinder rebuilt inside Halo Campaign Evolved",
    position: "center 42%",
  },
  {
    name: "Death Island",
    code: "DTI",
    slug: "ce-death-island",
    image: MULTIPLAYER_IMAGES.deathIsland,
    alt: "Coastal cliffs and Forerunner arches of Death Island in Halo Campaign Evolved",
    position: "center 45%",
  },
  {
    name: "Timberland",
    code: "TMB",
    slug: "ce-timberland",
    image: MULTIPLAYER_IMAGES.timberland,
    alt: "Pine forest valley and bases of Timberland in Halo Campaign Evolved",
    position: "center 45%",
  },
  {
    name: "Gephyrophobia",
    code: "GPH",
    slug: "ce-gephyrophobia",
    image: MULTIPLAYER_IMAGES.gephyrophobia,
    alt: "High chasm bridge and mist of Gephyrophobia in Halo Campaign Evolved",
    position: "center 45%",
  },
  {
    name: "Battle Creek",
    code: "BCK",
    slug: "ce-battle-creek",
    image: MULTIPLAYER_IMAGES.battleCreek,
    alt: "Stream canyon and opposing bases of Battle Creek in Halo Campaign Evolved",
    position: "center 48%",
  },
];

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
  { name: "Blood Gulch", slug: "ce-blood-gulch", code: "BGL", image: MULTIPLAYER_IMAGES.bloodGulch },
  { name: "Battle Creek", slug: "ce-battle-creek", code: "BCK", image: MULTIPLAYER_IMAGES.battleCreek },
  { name: "Sidewinder", slug: "ce-sidewinder", code: "SDW", image: MULTIPLAYER_IMAGES.sidewinder },
  { name: "Damnation", slug: "ce-damnation", code: "DMN", image: MULTIPLAYER_IMAGES.damnation },
  { name: "Rat Race", slug: "ce-rat-race", code: "RAT", image: MULTIPLAYER_IMAGES.ratRace },
  { name: "Prisoner", slug: "ce-prisoner", code: "PRS", image: MULTIPLAYER_IMAGES.prisoner },
  { name: "Hang 'Em High", slug: "ce-hang-em-high", code: "HEH", image: MULTIPLAYER_IMAGES.hangEmHigh },
  { name: "Chill Out", slug: "ce-chill-out", code: "CHL", image: MULTIPLAYER_IMAGES.chillOut },
  { name: "Derelict", slug: "ce-derelict", code: "DRL", image: MULTIPLAYER_IMAGES.derelict },
  { name: "Boarding Action", slug: "ce-boarding-action", code: "BDA", image: MULTIPLAYER_IMAGES.boardingAction },
  { name: "Chiron TL-34", slug: "ce-chiron-tl-34", code: "PTP", image: MULTIPLAYER_IMAGES.chiron },
  { name: "Longest", slug: "ce-longest", code: "LNG", image: MULTIPLAYER_IMAGES.longest },
  { name: "Wizard", slug: "ce-wizard", code: "WIZ", image: MULTIPLAYER_IMAGES.wizard },
  { name: "Danger Canyon", slug: "ce-danger-canyon", code: "DCN", image: MULTIPLAYER_IMAGES.dangerCanyon },
  { name: "Death Island", slug: "ce-death-island", code: "DTI", image: MULTIPLAYER_IMAGES.deathIsland },
  { name: "Gephyrophobia", slug: "ce-gephyrophobia", code: "GPH", image: MULTIPLAYER_IMAGES.gephyrophobia },
  { name: "Ice Fields", slug: "ce-ice-fields", code: "ICE", image: MULTIPLAYER_IMAGES.iceFields },
  { name: "Infinity", slug: "ce-infinity", code: "INF", image: MULTIPLAYER_IMAGES.infinity },
  { name: "Timberland", slug: "ce-timberland", code: "TMB", image: MULTIPLAYER_IMAGES.timberland },
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
    description: "Launch the game, open MULTIPLAYER, choose a map and mode, invite your friends, and start the game. Everyone needs the same maps installed; a player missing a hub map can download it from inside the game.",
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
    answer: "Up to 16 players, on every classic map. Each player needs their own PC and their own copy of the game, with the same maps installed; a missing hub map can be downloaded from inside the game, with no restart. More than two players on one PC isn't supported yet.",
    href: MULTIPLAYER_RELEASE_PATH,
    linkLabel: "See the alpha release notes",
  },
  {
    id: "requirements",
    question: "What do I need to play? Does it work with Game Pass?",
    answer: "You need Windows 10 or 11 (64-bit), the MJOLNIR Launcher, and your own copy of Halo Campaign Evolved. The multiplayer alpha works on both the Steam and the Xbox app / Game Pass versions, and Steam and Game Pass players can play in the same game. If a Steam player is dropped soon after joining a Game Pass host, check that the host's Xbox account allows cross-network play in its privacy settings. MJOLNIR is free and open source; the base game is a separate requirement.",
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
