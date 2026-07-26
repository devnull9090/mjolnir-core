import type { Metadata } from "next";
import Link from "next/link";
import { Boxes, FlaskConical, Map, Network, TriangleAlert } from "lucide-react";
import { EvidenceBadge } from "../../_components/EvidenceBadge";

export const metadata: Metadata = {
  title: "Multiplayer Investigation | MJOLNIR Docs",
  description:
    "Evidence, packed-content inventory, and staged experiments for multiplayer in Halo Campaign Evolved.",
};

const rootMaps = [
  "/Game/Levels/Halo1/Solo/A15/A15",
  "/Game/Levels/Halo1/Solo/A30/A30",
  "/Game/Levels/Halo1/Solo/A50/A50",
  "/Game/Levels/Halo1/Solo/B30/B30",
  "/Game/Levels/Halo1/Solo/B40/B40",
  "/Game/Levels/Halo1/Solo/C10/C10",
  "/Game/Levels/Halo1/Solo/C20/C20",
  "/Game/Levels/Halo1/Solo/C45/C45",
  "/Game/Levels/Halo1/Solo/D20/D20",
  "/Game/Levels/Halo1/Solo/D40/D40",
  "/Game/Levels/Halo1/Solo/Extra/E10/E10",
  "/Game/Levels/Halo1/Solo/Extra/E20/E20",
  "/Game/Levels/Halo1/Solo/Extra/E30/E30",
];

export default function MultiplayerResearchPage() {
  return (
    <main className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-9">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <EvidenceBadge level="Observed" />
          <span className="text-xs text-text-dim">CU2 content and binaries, checked 2026-07-26</span>
        </div>
        <div className="flex items-start gap-4">
          <FlaskConical className="mt-1 h-7 w-7 shrink-0 text-gold" />
          <div>
            <h1 className="text-3xl font-black sm:text-4xl">Multiplayer investigation</h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-text-muted">
              Halo Campaign Evolved ships four-player campaign co-op and a large amount of dormant
              competitive multiplayer machinery. The current goal is a minimal red-versus-blue CTF
              session in an existing campaign world, then a custom world once the runtime path is known.
            </p>
          </div>
        </div>
      </header>

      <section className="py-9" aria-labelledby="verdict-heading">
        <h2 id="verdict-heading" className="text-xl font-bold">
          Current verdict
        </h2>
        <div className="mt-5 border-l-2 border-gold bg-surface px-5 py-4">
          <p className="font-semibold text-foreground">No hidden multiplayer world package was found.</p>
          <p className="mt-2 text-sm leading-6 text-text-muted">
            The competitive rules, object definitions, messages, and simulation code remain, but this
            build does not expose a named multiplayer map in either content index.
          </p>
        </div>
        <div className="mt-6 grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["132,091", "unique IoStore paths"],
            ["14,240", "umap chunks"],
            ["77", "named non-generated maps"],
            ["0", "classic CE map names"],
          ].map(([value, label]) => (
            <div key={label} className="bg-background p-4">
              <p className="text-xl font-black text-gold">{value}</p>
              <p className="mt-1 text-xs uppercase text-text-dim">{label}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="content-heading">
        <div className="flex items-center gap-3">
          <Map className="h-5 w-5 text-gold" />
          <h2 id="content-heading" className="text-xl font-bold">
            Packed-content inventory
          </h2>
        </div>
        <ul className="mt-5 space-y-3 text-sm leading-6 text-text-muted">
          <li>All Halo world packages are under Levels/Halo1/Solo; there is no Multi branch.</li>
          <li>Eleven apparent CTF or KOTH map hits were random World Partition cell IDs.</li>
          <li>No Blood Gulch, Beaver Creek, Sidewinder, or other classic CE map name is indexed.</li>
          <li>The 27 companion pak files contain 200,029 entries, primarily Wwise audio and resources, with no map or asset package entries.</li>
          <li>The IoStore containers are indexed, Oodle-compressed UE5.5 containers and are not encrypted.</li>
        </ul>

        <details className="mt-6 border border-border bg-surface p-4">
          <summary className="cursor-pointer text-sm font-semibold text-foreground">
            Root world package paths
          </summary>
          <ul className="mt-4 grid gap-2 font-mono text-xs text-text-muted sm:grid-cols-2">
            {rootMaps.map((path) => (
              <li key={path} className="break-all">
                {path}
              </li>
            ))}
          </ul>
        </details>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="retained-heading">
        <div className="flex items-center gap-3">
          <Network className="h-5 w-5 text-gold" />
          <h2 id="retained-heading" className="text-xl font-bold">
            What remains
          </h2>
        </div>
        <div className="mt-5 grid gap-5 md:grid-cols-2">
          <div className="border border-border p-5">
            <EvidenceBadge level="Verified" />
            <h3 className="mt-4 font-bold">Packaged support assets</h3>
            <p className="mt-2 text-sm leading-6 text-text-muted">
              713 indexed paths sit under explicit multiplayer directories. They include multiplayer
              globals, object types, team names, messages, respawn audio, map overrides, loadouts,
              Megalo, Sandbox, the Oddball weapon, and assault-bomb assets.
            </p>
          </div>
          <div className="border border-border p-5">
            <EvidenceBadge level="Observed" />
            <h3 className="mt-4 font-bold">Simulation rules</h3>
            <p className="mt-2 text-sm leading-6 text-text-muted">
              The native simulation module contains CTF, Slayer, Oddball, King of the Hill,
              Infection, Juggernaut, Assault, Territories, Forge, team, respawn, and loadout
              identifiers. Presence does not yet prove that the shipping UE5 layer can activate them.
            </p>
          </div>
        </div>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="runtime-heading">
        <h2 id="runtime-heading" className="text-xl font-bold">
          Live runtime result
        </h2>
        <div className="mt-5 border-l-2 border-accent-green bg-surface px-5 py-4">
          <EvidenceBadge level="Verified" />
          <p className="mt-3 text-sm leading-6 text-text-muted">
            UE4SS found a live BlamEngineGlueOuterSubsystemImpl and four campaign variant objects.
            With A30 loaded, the campaign-flow subsystem owned one variant while three remained
            transient. The world scan found the A30 root world plus 90 World Partition cell worlds.
          </p>
        </div>
        <p className="mt-5 text-sm leading-6 text-text-muted">
          The exposed variant classes are BlamGameEngineBaseVariant and
          BlamGameEngineCampaignVariant. The previously suspected BlamGameEngineVariant path is not
          an exposed runtime class. Reflected APIs include social options, campaign flags,
          per-player traits, team ally/enemy/friendly/traitor tests, Blam player-index resolution,
          network co-op detection, session readiness, replicated session-running state, and endpoint
          IDs.
        </p>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          Fourteen high-level session, lobby, and travel hooks registered but produced no callbacks
          during the captured interval. This is an observation, not proof that the official flow
          bypasses them: tracing may have begun after an earlier transition. The next probe snapshots
          reflected variant and network-component state and traces endpoint assignment directly.
        </p>
        <div className="mt-5 border border-border p-5">
          <EvidenceBadge level="Verified" />
          <h3 className="mt-4 font-bold">Solo transition baseline</h3>
          <p className="mt-2 text-sm leading-6 text-text-muted">
            A controlled frontend-to-A30 run with no second player captured SetActiveCampaign. Four
            campaign variants appeared and CurrentCampaign resolved to DA_FirstPlayableCampaign.
            Endpoint generation advanced from 0 to 1, but both endpoint IDs stayed 0,
            bSessionRunning stayed false, and lobby player count stayed 1. Endpoint generation alone
            therefore does not prove a network peer exists.
          </p>
          <p className="mt-3 text-sm leading-6 text-text-muted">
            A second human tester is not currently available. The solo-versus-co-op differential,
            custom-travel session preservation, and competitive-mode activation remain unverified.
          </p>
        </div>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="route-heading">
        <div className="flex items-center gap-3">
          <Boxes className="h-5 w-5 text-gold" />
          <h2 id="route-heading" className="text-xl font-bold">
            Shortest prototype route
          </h2>
        </div>
        <ol className="mt-5 space-y-5 text-sm leading-6 text-text-muted">
          <li>
            <span className="font-bold text-foreground">1. Reuse co-op transport.</span> Host and join
            through the supported campaign session flow so PlayFab, Party, identity, and replication
            already work. Compare a real two-human capture against the recorded solo baseline.
          </li>
          <li>
            <span className="font-bold text-foreground">2. Travel to a known campaign world.</span> Test
            plain travel first, then the same path with a listen-server option. A15 is the smallest
            initial target: /Game/Levels/Halo1/Solo/A15/A15.
          </li>
          <li>
            <span className="font-bold text-foreground">3. Activate a game variant.</span> Discover the
            live base and campaign variant objects, then trace the shell startup structures that
            choose campaign versus CTF.
          </li>
          <li>
            <span className="font-bold text-foreground">4. Supply map metadata.</span> Campaign maps do
            not necessarily contain team spawns, flag stands, boundaries, or objective markers. Spawn
            these at runtime before treating the mode as playable.
          </li>
        </ol>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="custom-heading">
        <h2 id="custom-heading" className="text-xl font-bold">
          Custom-map path
        </h2>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          A custom map is a second-stage problem. The game can index unencrypted UE5.5 IoStore
          containers, and Retoc can produce pak, utoc, and ucas output. The unresolved constraint is
          cooking a compatible UE5.5 world with the game&apos;s custom versions, script imports, and
          required Blam components. A tiny travel-only test world should precede a full CTF arena.
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="warning-heading">
        <div className="flex items-center gap-3">
          <TriangleAlert className="h-5 w-5 text-gold" />
          <h2 id="warning-heading" className="text-xl font-bold">
            Repository status
          </h2>
        </div>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          MJOLNIRMultiplayer now uses the verified CU2 root-world paths and dispatches plain or
          listen-server travel through the live player controller. It still does not create or
          advertise a session, and travel has not yet been verified in HCE.
        </p>
        <pre className="mt-5 overflow-x-auto border border-border bg-surface p-4 text-xs leading-6 text-text-muted">
          <code>{`mjolnir_maps
mjolnir_travel a15
mjolnir_listen a15
mjolnir_scan_blam
mjolnir_scan_worlds
mjolnir_trace_network
mjolnir_dump_state`}</code>
        </pre>
      </section>

      <section className="border-t border-border py-9 text-sm text-text-muted">
        <p>
          Working notes and reproduction history are rendered in full at{" "}
          <Link
            href="/docs/notes/multiplayer-investigation-notes"
            className="text-gold hover:underline"
          >
            Multiplayer investigation notes
          </Link>
          .
        </p>
      </section>
    </main>
  );
}