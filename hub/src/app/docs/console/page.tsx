import type { Metadata } from "next";
import Link from "next/link";
import { Globe, Terminal, Wrench } from "lucide-react";
import { EvidenceBadge } from "../_components/EvidenceBadge";
import {
  getConsoleBuild,
  getConsoleFamilies,
  getConsoleTotals,
} from "@/lib/console";
import { ConsoleSearch } from "./ConsoleSearch";

const totals = getConsoleTotals();

export const metadata: Metadata = {
  title: "Halo Campaign Evolved console commands | MJOLNIR Docs",
  description:
    `Every Blam console command and HS script function in Halo Campaign Evolved: ${totals.names.toLocaleString()} names ` +
    `with signatures, return types and which ${totals.stubs} are compiled out of the release build, plus the ` +
    `${totals.globals} engine globals. Read from the shipped simulation DLL.`,
  keywords: [
    "Halo Campaign Evolved console commands",
    "Halo Campaign Evolved cheats",
    "Blam console",
    "HS script functions",
    "Halo scripting reference",
    "Halo modding",
  ],
  alternates: { canonical: "/docs/console" },
};

export default function ConsoleIndexPage() {
  const families = getConsoleFamilies();
  const build = getConsoleBuild();

  return (
    <main className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-9">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <EvidenceBadge level="Verified" />
          {build && (
            <span className="text-xs text-text-dim">Build {build}</span>
          )}
        </div>
        <div className="flex items-start gap-4">
          <Terminal className="mt-1 h-7 w-7 shrink-0 text-gold" />
          <div>
            <h1 className="break-words text-3xl font-black sm:text-4xl">
              Console commands
            </h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-text-muted">
              Every function the Blam engine inside Halo Campaign Evolved will
              accept at its console, with the signature it expects and whether
              this build still carries the code behind it. Read from the
              function table in the shipped simulation DLL, not from an older
              Halo.
            </p>
          </div>
        </div>

        <dl className="mt-7 grid grid-cols-2 gap-px border border-border bg-border sm:grid-cols-4">
          {[
            ["Functions", totals.names.toLocaleString()],
            ["Work in this build", totals.live.toLocaleString()],
            ["Compiled out", totals.stubs.toLocaleString()],
            [
              "Globals",
              `${totals.globals} · ${totals.globals - totals.deadGlobals} live`,
            ],
          ].map(([label, value]) => (
            <div key={label} className="bg-background px-4 py-4">
              <dt className="text-xs uppercase text-text-dim">{label}</dt>
              <dd className="mt-1 font-mono text-lg text-gold">{value}</dd>
            </div>
          ))}
        </dl>
      </header>

      <section className="py-9" aria-labelledby="search-heading">
        <h2 id="search-heading" className="sr-only">
          Search console commands
        </h2>
        <ConsoleSearch
          families={families}
          names={totals.names}
          globals={totals.globals}
        />
      </section>

      <section
        className="border-t border-border py-9"
        aria-labelledby="families-heading"
      >
        <h2 id="families-heading" className="text-xl font-bold">
          By family
        </h2>
        <p className="mt-2 text-sm text-text-muted">
          Names share a prefix with the system they belong to. Each family is
          one page, with every function anchored.
        </p>
        <ul className="mt-6 grid grid-cols-1 gap-px border border-border bg-border sm:grid-cols-2">
          {families.map((family) => (
            <li key={family.slug} className="bg-background">
              <Link
                href={`/docs/console/${family.slug}`}
                className="group flex h-full flex-col px-5 py-4 transition-colors hover:bg-surface"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-semibold group-hover:text-gold">
                    {family.title}
                  </span>
                  <span className="shrink-0 font-mono text-xs text-text-muted">
                    {family.count}
                    {family.stubs > 0 && (
                      <span className="text-text-dim">
                        {" "}
                        · {family.stubs} out
                      </span>
                    )}
                  </span>
                </div>
                {family.sample.length > 0 ? (
                  <p className="mt-1 truncate font-mono text-xs text-text-dim">
                    {family.sample.join(" · ")}
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-text-dim">
                    Nothing in this family runs.
                  </p>
                )}
              </Link>
            </li>
          ))}
          <li className="bg-background">
            <Link
              href="/docs/console/globals"
              className="group flex h-full flex-col px-5 py-4 transition-colors hover:bg-surface"
            >
              <div className="flex items-baseline justify-between gap-3">
                <span className="flex items-center gap-2 font-semibold group-hover:text-gold">
                  <Globe className="h-4 w-4 text-gold" aria-hidden />
                  Globals
                </span>
                <span className="shrink-0 font-mono text-xs text-text-muted">
                  {totals.globals}
                  <span className="text-text-dim">
                    {" "}
                    · {totals.deadGlobals} no storage
                  </span>
                </span>
              </div>
              <p className="mt-1 truncate font-mono text-xs text-text-dim">
                game_speed · cheat_deathless_player · console_pauses_game
              </p>
            </Link>
          </li>
        </ul>
      </section>

      <section
        className="border-t border-border py-9"
        aria-labelledby="using-heading"
      >
        <div className="flex items-center gap-3">
          <Wrench className="h-5 w-5 text-gold" />
          <h2 id="using-heading" className="text-xl font-bold">
            Running them
          </h2>
        </div>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          The game ships the console but nothing feeds it. The
          MJOLNIRBlamConsole mod in the code-mod set wires the Unreal console to
          it: type a name with its arguments and the engine compiles and runs
          the line on its simulation thread. A bare name needs no punctuation; a
          nested expression takes the{" "}
          <code className="font-mono text-gold">blam</code> prefix.
        </p>
        <pre className="mt-4 overflow-x-auto border border-border bg-surface p-4 font-mono text-xs leading-6 text-text-muted">
          {`ai_enabled                              = true  (boolean)
player_teleport player0 my_flag
fade_out 0 0 0 30
blam (unit_get_health (player0))        = 1.000000  (real)
help object_                            every name containing "object_"`}
        </pre>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          Answers show on screen and on the UE4SS console. A function marked{" "}
          <span className="border border-border-bright bg-surface-raised px-1.5 py-0.5 text-[10px] font-bold uppercase text-text-muted">
            compiled out
          </span>{" "}
          is accepted and does nothing: the release build replaced its body with
          a shared stub, and every <code className="font-mono">cheat_*</code> is
          among them. A global marked{" "}
          <span className="border border-border-bright bg-surface-raised px-1.5 py-0.5 text-[10px] font-bold uppercase text-text-muted">
            no storage
          </span>{" "}
          reads as zero and ignores writes.
        </p>
        <p className="mt-4 text-sm text-text-muted">
          How the mod works, and what it took to find the console:{" "}
          <Link
            href="/docs/notes/blam-console"
            className="text-gold hover:underline"
          >
            The Blam console
          </Link>
          .
        </p>
      </section>

      <section
        className="border-t border-border py-9"
        aria-labelledby="about-heading"
      >
        <h2 id="about-heading" className="text-xl font-bold">
          Where this comes from
        </h2>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          The simulation DLL carries the engine&apos;s function table:{" "}
          {totals.entries.toLocaleString()} slots, one per overload, each with a
          name, typed parameters, a return type and the address of its
          evaluator. The <code className="font-mono">mjolnir console</code>{" "}
          command reads that table and the globals array out of the PE image,
          and marks the slots whose evaluator is the shared stub. The help
          strings are the one thing the table no longer has: the release build
          nulled every one, so the descriptions here are written by hand and
          cover {totals.described} functions so far.
        </p>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          Where a function is called by the shipped campaign scripts, the page
          says how often and with how many arguments. That is observed usage,
          recovered from the compiled scripts, not a declaration.
        </p>
      </section>
    </main>
  );
}
