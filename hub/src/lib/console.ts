import consoleIndex from "@/generated/console-index.json";
import consoleDefs from "@/generated/console-defs.json";

export type ConsoleSignature = {
  /** Slot in the engine's function table; the opcode compiled scripts use. */
  index: number;
  params: string[];
  /** Free-form parameter text for special forms, which have no typed list. */
  text: string | null;
  returns: string;
  stub: boolean;
  special: boolean;
};

export type ConsoleUsage = {
  calls: number;
  minArgs: number;
  maxArgs: number;
  quoted: boolean[];
};

export type ConsoleFunction = {
  name: string;
  anchor: string;
  signatures: ConsoleSignature[];
  usage: ConsoleUsage | null;
  /** True only if every overload is compiled out. */
  stub: boolean;
  returns: string[];
  description: string | null;
};

export type ConsoleFamily = {
  slug: string;
  title: string;
  description: string | null;
  functions: ConsoleFunction[];
};

export type ConsoleFamilySummary = {
  slug: string;
  title: string;
  count: number;
  live: number;
  stubs: number;
  described: number;
  sample: string[];
};

export type ConsoleGlobal = {
  name: string;
  anchor: string;
  type: string;
  dead: boolean;
  index: number;
  description: string | null;
};

type ConsoleIndex = {
  build: string;
  totals: {
    entries: number;
    names: number;
    live: number;
    stubs: number;
    entryStubs: number;
    globals: number;
    deadGlobals: number;
    families: number;
    described: number;
  };
  families: ConsoleFamilySummary[];
};

type ConsoleDefs = {
  generator: string;
  build: string;
  source: string;
  families: Record<string, ConsoleFamily>;
  globals: ConsoleGlobal[];
};

const index = consoleIndex as ConsoleIndex;
const defs = consoleDefs as unknown as ConsoleDefs;

export function getConsoleBuild(): string {
  return index.build;
}

export function getConsoleTotals() {
  return index.totals;
}

/** Every family summary, largest first, catch-alls last. */
export function getConsoleFamilies(): ConsoleFamilySummary[] {
  return index.families;
}

export function getConsoleFamilySummary(
  slug: string,
): ConsoleFamilySummary | undefined {
  return index.families.find((f) => f.slug === slug);
}

export function getConsoleFamily(slug: string): ConsoleFamily | undefined {
  return defs.families[slug];
}

export function getConsoleGlobals(): ConsoleGlobal[] {
  return defs.globals;
}

/** The HS form of one signature: `(name <type> <type>)`. */
export function signatureText(name: string, sig: ConsoleSignature): string {
  if (sig.text) return `(${name} ${sig.text})`;
  const params = sig.params.map((p) => `<${p}>`).join(" ");
  return params ? `(${name} ${params})` : `(${name})`;
}

/**
 * What to type at the Unreal console with the MJOLNIR Blam console installed.
 * Bare names go straight in; anything nested needs the `blam` prefix.
 */
export function consoleForm(name: string, sig: ConsoleSignature): string {
  if (sig.special || sig.text) return `blam ${signatureText(name, sig)}`;
  if (!/^[a-z_][a-z0-9_]*$/i.test(name))
    return `blam ${signatureText(name, sig)}`;
  const params = sig.params.map((p) => `<${p}>`).join(" ");
  return params ? `${name} ${params}` : name;
}
