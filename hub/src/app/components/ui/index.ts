/**
 * The hub's own design system: page frame, headers, filters, figures and
 * the match-specific pieces (avatars, podium places, map covers). Hub-only,
 * so it styles with this site's Tailwind theme names; anything the launcher
 * shares lives in src/kit/ui and styles against the --mj-* tokens instead.
 */
export { PageShell } from "./PageShell";
export { ButtonLink, PageHeader, SectionHeading } from "./PageHeader";
export { FilterBar, FilterChips, SelectNav, ToggleChip, type FilterOption } from "./Filters";
export { ViewToggle } from "./ViewToggle";
export { EmptyState, Pager, Pill, StatGrid, StatTile, TableFrame } from "./Display";
export { MapCover } from "./MapCover";
export {
  PlaceBadge,
  PlayerAvatar,
  TEAM_BG,
  TEAM_BORDER,
  TEAM_TEXT,
  TeamDot,
  WinnerTag,
  ordinal,
} from "./Players";
