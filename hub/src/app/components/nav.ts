/**
 * Single source of truth for site navigation.
 * Desktop uses 5 top-level slots (2 dropdown menus + 3 direct links) so the
 * bar never crowds at any desktop width, signed in or signed out.
 */

export type NavIconKey =
  | "gamepad"
  | "radio"
  | "swords"
  | "trophy"
  | "map"
  | "package"
  | "book"
  | "wrench"
  | "blocks"
  | "scroll"
  | "newspaper";

export interface NavLeaf {
  href: string;
  label: string;
  description: string;
  icon: NavIconKey;
}

export type DesktopNavEntry =
  | {
      kind: "link";
      href: string;
      label: string;
      icon: NavIconKey;
    }
  | {
      kind: "group";
      id: string;
      label: string;
      items: readonly NavLeaf[];
    };

export const DESKTOP_NAV: readonly DesktopNavEntry[] = [
  {
    kind: "group",
    id: "play",
    label: "Play",
    items: [
      {
        href: "/multiplayer",
        label: "Multiplayer",
        description: "Alpha overview, modes & setup FAQ",
        icon: "gamepad",
      },
      {
        href: "/games",
        label: "Live Games",
        description: "Open public lobbies & 1-click joins",
        icon: "radio",
      },
      {
        href: "/matches",
        label: "Matches",
        description: "Recent scoreboards & 3D kill maps",
        icon: "swords",
      },
      {
        href: "/leaderboards",
        label: "Players",
        description: "Leaderboards & combat records",
        icon: "trophy",
      },
    ],
  },
  { kind: "link", href: "/maps", label: "Maps", icon: "map" },
  { kind: "link", href: "/mods", label: "Mods", icon: "package" },
  {
    kind: "group",
    id: "create",
    label: "Create",
    items: [
      {
        href: "/docs",
        label: "Docs",
        description: "Guides, tag reference & API",
        icon: "book",
      },
      {
        href: "/tools",
        label: "Tools",
        description: "Tag Editor, CLI & Blender addon",
        icon: "wrench",
      },
      {
        href: "/forge",
        label: "Forge Packs",
        description: "Modular Forge building kits",
        icon: "blocks",
      },
      {
        href: "/changelog",
        label: "Changelog",
        description: "Release history across all products",
        icon: "scroll",
      },
    ],
  },
  { kind: "link", href: "/blog", label: "Blog", icon: "newspaper" },
];

/**
 * Whether a nav entry matches the current pathname.
 * Player profile pages belong under Players (/leaderboards).
 */
export function isActive(href: string, pathname: string): boolean {
  if (href === "/leaderboards" && pathname.startsWith("/players")) return true;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function isGroupActive(items: readonly NavLeaf[], pathname: string): boolean {
  return items.some((item) => isActive(item.href, pathname));
}
