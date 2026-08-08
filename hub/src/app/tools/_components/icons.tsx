import type { ComponentType } from "react";
import { FileCode2, TerminalSquare } from "lucide-react";

import type { ToolIcon as ToolIconKey } from "@/lib/tools";

/**
 * The registry stores an icon key rather than a component, so `lib/tools.ts`
 * stays importable by the API worker. This is where a key becomes a picture.
 *
 * A component rather than a `key => Component` lookup used at the call site:
 * resolving one during render reads to React's lint rules as a component
 * defined during render, which is the thing that remounts subtrees.
 */
const ICONS: Record<ToolIconKey, ComponentType<{ className?: string }>> = {
  "file-code": FileCode2,
  terminal: TerminalSquare,
};

export function ToolIcon({ name, className }: { name: ToolIconKey; className?: string }) {
  const Icon = ICONS[name];
  return <Icon className={className} />;
}
