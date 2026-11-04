/** The site's sections, once: the desktop bar, the mobile drawer and the active marker all read this. */
export const DESKTOP_NAV = [
  { href: "/multiplayer", label: "Multiplayer" },
  { href: "/mods", label: "Mods" },
  { href: "/maps", label: "Maps" },
  { href: "/games", label: "Games" },
  { href: "/matches", label: "Matches" },
  { href: "/tools", label: "Tools" },
  { href: "/docs", label: "Docs" },
  { href: "/blog", label: "Blog" },
] as const;

/**
 * Whether a nav entry is the section the reader is in. A match or player
 * page belongs to Matches; a profile has no section.
 */
export function isActive(href: string, pathname: string): boolean {
  if (href === "/mods" && pathname === "/forge") return true;
  if (href === "/matches" && pathname.startsWith("/players")) return true;
  return pathname === href || pathname.startsWith(`${href}/`);
}
