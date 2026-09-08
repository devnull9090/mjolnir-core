// Generates the Blam console reference artifacts consumed by /docs/console.
//
// The function table and the globals array come from `mjolnir console`, which
// reads them out of the simulation DLL (defs/hce/console.json). The release
// build ships every function's help pointer as null, so what the engine gives
// us is names, parameter types, return types and which functions were compiled
// out — not what they do. Two more sources fill that in where they can:
//
//   defs/hce/scripting.json            how the shipped campaign scripts call
//                                      each function (observed, not declared)
//   defs/hce/console-descriptions.json hand-written descriptions, merged by
//                                      name; missing entries render fine
//
// Three artifacts are written, matching sync-tag-defs.mjs:
//   src/generated/console-defs.json   every family with its functions, used
//                                     only at build time to render one page
//                                     per family
//   src/generated/console-index.json  family summaries and totals, imported
//                                     directly
//   public/console-search.json        one row per name, fetched on demand by
//                                     the search box

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const hubDir = path.resolve(scriptDir, "..");
const defsDir = path.resolve(hubDir, "..", "defs", "hce");
const consoleFile = path.join(defsDir, "console.json");
const scriptingFile = path.join(defsDir, "scripting.json");
const descriptionsFile = path.join(defsDir, "console-descriptions.json");
const generatedDir = path.join(hubDir, "src", "generated");
const publicDir = path.join(hubDir, "public");
const defsOut = path.join(generatedDir, "console-defs.json");
const indexOut = path.join(generatedDir, "console-index.json");
const searchOut = path.join(publicDir, "console-search.json");

/** A prefix needs this many distinct names before it is a family of its own. */
const FAMILY_MIN = 4;

/** Prefixes folded into a neighbour so `object_*` and `objects_*` share a page. */
const MERGES = {
  objects: "object",
  players: "player",
  units: "unit",
  event: "events",
  network: "net",
  achievements: "achievement",
};

/** Human titles for the prefixes that have them; the rest use the prefix itself. */
const TITLES = {
  ai: "AI",
  unit: "Units",
  cs: "Command scripts",
  player: "Players",
  cinematic: "Cinematics",
  object: "Objects",
  game: "Game state",
  survival: "Firefight",
  chud: "HUD",
  debug: "Debugging",
  sound: "Sound",
  net: "Networking",
  objectives: "Objectives",
  camera: "Camera",
  render: "Rendering",
  device: "Devices",
  events: "Events",
  vehicle: "Vehicles",
  mantini: "Mantini",
  mp: "Multiplayer",
  cui: "UI screens",
  controller: "Controllers",
  saved: "Saved films",
  tag: "Tags",
  simulation: "Simulation",
  havok: "Havok physics",
  flock: "Flocks",
  performance: "Performance",
  volume: "Volumes",
  scenery: "Scenery",
  thespian: "Thespian",
  core: "Core",
  submit: "Submit",
  effect: "Effects",
  damage: "Damage",
  dump: "Dumps",
  ui: "UI",
  determinism: "Determinism",
  incidents: "Incidents",
  animation: "Animation",
  campaign: "Campaign",
  scenario: "Scenario",
  auto: "Auto",
  map: "Map",
  custom: "Custom",
  cheat: "Cheats",
  error: "Errors",
  interpolator: "Interpolators",
  script: "Script language",
  fade: "Fades",
  kill: "Kill volumes",
  physics: "Physics",
  drop: "Drop",
  director: "Director",
  pvs: "Visibility",
  main: "Main loop",
  shader: "Shaders",
  flags: "Editor flags",
  skull: "Skulls",
  console: "Console",
  meteorite: "Meteorite additions",
  other: "Everything else",
};

/**
 * The HS language itself: special forms, operators, casts, the sleep family,
 * printing. The function table carries these alongside the engine API, and
 * the prefix rule would scatter them across a dozen families.
 */
const SCRIPT_NAMES = new Set([
  "begin",
  "begin_random",
  "begin_count",
  "begin_random_count",
  "if",
  "cond",
  "set",
  "and",
  "or",
  "not",
  "+",
  "-",
  "*",
  "/",
  "%",
  "min",
  "max",
  "=",
  "!=",
  ">",
  "<",
  ">=",
  "<=",
  "sleep",
  "sleep_forever",
  "sleep_until",
  "sleep_until_game_ticks",
  "wake",
  "cinematic_sleep",
  "inspect",
  "branch",
  "unit",
  "vehicle",
  "weapon",
  "device",
  "scenery",
  "evaluate",
  "pin",
  "abs_integer",
  "abs_real",
  "bitwise_and",
  "bitwise_or",
  "bitwise_xor",
  "bitwise_left_shift",
  "bitwise_right_shift",
  "bit_test",
  "bit_toggle",
  "bitwise_flags_toggle",
  "print",
  "print_if",
  "log_print",
  "breakpoint",
  "kill_active_scripts",
  "kill_thread",
  "get_executing_running_thread",
  "script_started",
  "script_finished",
  "random_range",
  "real_random_range",
  "list_get",
  "list_count",
  "list_count_not_dead",
  "object_list_get",
  "object_list_count",
]);

/** Console-only commands: no prefix, lowercase, not part of the language. */
const CONSOLE_NAMES = new Set([
  "help",
  "cls",
  "find",
  "version",
  "crash",
  "status",
  "drop",
]);

const OPERATOR_ANCHORS = {
  "+": "op-plus",
  "-": "op-minus",
  "*": "op-times",
  "/": "op-divide",
  "%": "op-modulo",
  "=": "op-equal",
  "!=": "op-not-equal",
  ">": "op-greater",
  "<": "op-less",
  ">=": "op-greater-equal",
  "<=": "op-less-equal",
};

function anchorFor(name) {
  if (OPERATOR_ANCHORS[name]) return OPERATOR_ANCHORS[name];
  return name.toLowerCase().replace(/[^a-z0-9_]+/g, "-");
}

function prefixOf(name) {
  const i = name.indexOf("_");
  return i > 0 ? name.slice(0, i) : "";
}

/** Signature text the way the mod's `help` prints it. */
function signatureText(name, sig) {
  if (sig.text) return `(${name} ${sig.text})`;
  const params = sig.params.map((p) => `<${p}>`).join(" ");
  return params ? `(${name} ${params})` : `(${name})`;
}

async function readJson(file, fallback) {
  try {
    return JSON.parse(await readFile(file, "utf8"));
  } catch {
    return fallback;
  }
}

async function writeEmpty() {
  await mkdir(generatedDir, { recursive: true });
  await mkdir(publicDir, { recursive: true });
  await writeFile(
    defsOut,
    JSON.stringify({ generator: "", build: "", families: {}, globals: [] }),
  );
  await writeFile(
    indexOut,
    JSON.stringify({
      build: "",
      totals: {
        entries: 0,
        names: 0,
        live: 0,
        stubs: 0,
        globals: 0,
        deadGlobals: 0,
        families: 0,
      },
      families: [],
    }),
  );
  await writeFile(searchOut, JSON.stringify([]));
}

async function main() {
  const corpus = await readJson(consoleFile, null);
  if (!corpus) {
    console.warn(
      `[sync-console-defs] ${path.relative(hubDir, consoleFile)} not found; skipping. ` +
        "Run `mjolnir console` against an installed game to generate it.",
    );
    await writeEmpty();
    return;
  }
  const scripting = await readJson(scriptingFile, { functions: {} });
  const descriptions = await readJson(descriptionsFile, {
    functions: {},
    families: {},
  });

  // One entry per name; the engine overloads by argument count, and each
  // overload is its own slot in the table.
  const byName = new Map();
  for (const f of corpus.functions ?? []) {
    let entry = byName.get(f.name);
    if (!entry) {
      entry = {
        name: f.name,
        anchor: anchorFor(f.name),
        signatures: [],
        usage: null,
      };
      byName.set(f.name, entry);
    }
    entry.signatures.push({
      index: f.index,
      params: f.parameters ?? [],
      text: f.parameters_text ?? null,
      returns: f.returns,
      stub: Boolean(f.stub),
      special: f.flags === 2,
    });
    const observed = scripting.functions?.[String(f.index)];
    if (observed && !entry.usage) {
      const calls = Object.values(observed.returns ?? {}).reduce(
        (n, c) => n + c,
        0,
      );
      if (calls > 0) {
        entry.usage = {
          calls,
          minArgs: observed.min_args ?? 0,
          maxArgs: observed.max_args ?? 0,
          quoted: (observed.parameters ?? []).map((p) => Boolean(p.quoted)),
        };
      }
    }
  }
  for (const entry of byName.values()) {
    entry.signatures.sort((a, b) => a.index - b.index);
    // A name is compiled out only if every overload is.
    entry.stub = entry.signatures.every((s) => s.stub);
    entry.returns = [...new Set(entry.signatures.map((s) => s.returns))];
    entry.description = descriptions.functions?.[entry.name] ?? null;
  }

  // Family assignment: prefixes with enough names, a few merges, and the
  // language and console sets pulled out first.
  const prefixCounts = new Map();
  for (const name of byName.keys()) {
    if (SCRIPT_NAMES.has(name) || CONSOLE_NAMES.has(name)) continue;
    const raw = prefixOf(name);
    const p = MERGES[raw] ?? raw;
    if (p) prefixCounts.set(p, (prefixCounts.get(p) ?? 0) + 1);
  }
  const familyOf = (name) => {
    if (SCRIPT_NAMES.has(name)) return "script";
    if (CONSOLE_NAMES.has(name)) return "console";
    if (/^[A-Z]/.test(name)) return "meteorite";
    const raw = prefixOf(name);
    const p = MERGES[raw] ?? raw;
    return p && (prefixCounts.get(p) ?? 0) >= FAMILY_MIN ? p : "other";
  };

  const families = {};
  for (const entry of byName.values()) {
    const slug = familyOf(entry.name);
    if (!families[slug]) {
      families[slug] = {
        slug,
        title: TITLES[slug] ?? slug,
        description: descriptions.families?.[slug] ?? null,
        functions: [],
      };
    }
    families[slug].functions.push(entry);
  }
  for (const family of Object.values(families)) {
    family.functions.sort((a, b) => a.name.localeCompare(b.name));
  }

  const globals = (corpus.globals ?? [])
    .map((g) => ({
      name: g.name,
      anchor: anchorFor(g.name),
      type: g.type,
      dead: Boolean(g.dead),
      index: g.index,
      description: descriptions.globals?.[g.name] ?? null,
    }))
    .sort((a, b) => a.name.localeCompare(b.name));

  const slugs = Object.keys(families).sort((a, b) => {
    // Largest families first, with the catch-alls last regardless of size.
    const tail = (s) =>
      s === "other" ? 2 : s === "meteorite" || s === "console" ? 1 : 0;
    return (
      tail(a) - tail(b) ||
      families[b].functions.length - families[a].functions.length ||
      a.localeCompare(b)
    );
  });

  const summaries = slugs.map((slug) => {
    const f = families[slug];
    const live = f.functions.filter((fn) => !fn.stub).length;
    return {
      slug,
      title: f.title,
      count: f.functions.length,
      live,
      stubs: f.functions.length - live,
      described: f.functions.filter((fn) => fn.description).length,
      sample: f.functions
        .filter((fn) => !fn.stub)
        .slice(0, 4)
        .map((fn) => fn.name),
    };
  });

  const entries = corpus.functions?.length ?? 0;
  const names = byName.size;
  const stubs = [...byName.values()].filter((e) => e.stub).length;
  const entryStubs = (corpus.functions ?? []).filter((f) => f.stub).length;
  const deadGlobals = globals.filter((g) => g.dead).length;

  // Search rows: [name, family slug, anchor, stub, first signature text].
  // Compact on purpose; the file is fetched by the browser on first keystroke.
  const search = [];
  for (const slug of slugs) {
    for (const fn of families[slug].functions) {
      search.push([
        fn.name,
        slug,
        fn.anchor,
        fn.stub ? 1 : 0,
        signatureText(fn.name, fn.signatures[0]),
      ]);
    }
  }
  for (const g of globals) {
    search.push([
      g.name,
      "globals",
      g.anchor,
      g.dead ? 1 : 0,
      `global ${g.type}`,
    ]);
  }

  await mkdir(generatedDir, { recursive: true });
  await mkdir(publicDir, { recursive: true });
  await writeFile(
    defsOut,
    JSON.stringify({
      generator: "scripts/sync-console-defs.mjs",
      build: corpus.build ?? "",
      source: corpus.generator ?? "",
      families,
      globals,
    }),
  );
  await writeFile(
    indexOut,
    `${JSON.stringify(
      {
        build: corpus.build ?? "",
        totals: {
          entries,
          names,
          live: names - stubs,
          stubs,
          entryStubs,
          globals: globals.length,
          deadGlobals,
          families: slugs.length,
          described: [...byName.values()].filter((e) => e.description).length,
        },
        families: summaries,
      },
      null,
      2,
    )}\n`,
  );
  await writeFile(searchOut, JSON.stringify(search));

  console.log(
    `sync-console-defs: ${names} names (${entries} table entries, ${stubs} compiled out) in ` +
      `${slugs.length} families, ${globals.length} globals (${deadGlobals} without storage)`,
  );
}

await main();
