import type { Metadata } from "next";
import Link from "next/link";
import { Globe } from "lucide-react";
import { EvidenceBadge } from "../../_components/EvidenceBadge";
import {
  getConsoleBuild,
  getConsoleGlobals,
  getConsoleTotals,
  type ConsoleGlobal,
} from "@/lib/console";

const totals = getConsoleTotals();

export const metadata: Metadata = {
  title: "Halo Campaign Evolved engine globals | MJOLNIR Docs",
  description:
    `The ${totals.globals} engine globals of the Halo Campaign Evolved Blam console, from game_speed to ` +
    `cheat_deathless_player, with their types and which ${totals.deadGlobals} have no storage in the release build.`,
  keywords: [
    "Halo Campaign Evolved globals",
    "game_speed",
    "cheat_deathless_player",
    "Blam console",
    "Halo Campaign Evolved cheats",
  ],
  alternates: { canonical: "/docs/console/globals" },
};

function GlobalsTable({ rows }: { rows: ConsoleGlobal[] }) {
  return (
    <div className="mt-5 overflow-x-auto border border-border">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead className="bg-surface text-xs uppercase text-text-dim">
          <tr>
            <th className="px-4 py-3">Global</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Description</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.map((g) => (
            <tr key={g.name} id={g.anchor} className="scroll-mt-24 align-top">
              <td className="px-4 py-3 font-mono text-xs text-gold">
                {g.name}
              </td>
              <td className="px-4 py-3 font-mono text-xs text-text-muted">
                {g.type}
              </td>
              <td className="px-4 py-3 text-xs text-text-muted">
                {g.description ?? <span className="text-text-dim">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ConsoleGlobalsPage() {
  const globals = getConsoleGlobals();
  const build = getConsoleBuild();
  const live = globals.filter((g) => !g.dead);
  const dead = globals.filter((g) => g.dead);

  return (
    <main className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-9">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <EvidenceBadge level="Verified" />
          <Link
            href="/docs/console"
            className="text-xs text-gold hover:underline"
          >
            All console commands
          </Link>
          {build && (
            <span className="text-xs text-text-dim">Build {build}</span>
          )}
        </div>
        <div className="flex items-start gap-4">
          <Globe className="mt-1 h-7 w-7 shrink-0 text-gold" />
          <div className="min-w-0">
            <h1 className="break-words text-3xl font-black sm:text-4xl">
              Engine globals
            </h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-text-muted">
              Named engine variables the console reads and writes: type the name
              alone to read it, or the name and a value to set it. In this build
              most of them are names without a variable behind them: they read
              as zero and ignore writes, and the console says so.
            </p>
          </div>
        </div>

        <dl className="mt-7 grid grid-cols-2 gap-px border border-border bg-border">
          {[
            ["With storage", live.length.toLocaleString()],
            ["No storage in this build", dead.length.toLocaleString()],
          ].map(([label, value]) => (
            <div key={label} className="bg-background px-4 py-4">
              <dt className="text-xs uppercase text-text-dim">{label}</dt>
              <dd className="mt-1 font-mono text-base text-gold">{value}</dd>
            </div>
          ))}
        </dl>
      </header>

      <section
        className="border-b border-border py-9"
        aria-labelledby="live-heading"
      >
        <h2 id="live-heading" className="text-xl font-bold">
          With storage
        </h2>
        <p className="mt-2 text-sm text-text-muted">
          These have a variable in the simulation DLL. Reading returns its
          current value; writing changes it.
        </p>
        <GlobalsTable rows={live} />
      </section>

      <section className="py-9" aria-labelledby="dead-heading">
        <h2 id="dead-heading" className="text-xl font-bold">
          No storage in this build
        </h2>
        <p className="mt-2 text-sm text-text-muted">
          The name survives in the globals array, but its storage pointer is
          null. The classic cheats are all here.
        </p>
        <GlobalsTable rows={dead} />
      </section>
    </main>
  );
}
