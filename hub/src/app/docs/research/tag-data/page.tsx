import type { Metadata } from "next";
import Link from "next/link";
import { AlertTriangle, Boxes, Layers, Package } from "lucide-react";
import { EvidenceBadge } from "../../_components/EvidenceBadge";

export const metadata: Metadata = {
  title: "Blam tag data | MJOLNIR Docs",
  description:
    "Halo Campaign Evolved ships 12,328 real Blam tag files inside Unreal packages. Evidence, container format, and reproduction steps.",
};

const headerFields: Array<[string, string, string]> = [
  ["0x30", "Group four-CC (bipd, weap, vehi, sbsp)", "Verified"],
  ["0x34", "Small group-constant integer", "Observed"],
  ["0x38", "Per-tag 32-bit value", "Observed"],
  ["0x3C", "BLAM signature", "Verified"],
  ["0x40", "tag! signature", "Verified"],
  ["0x48", "Payload size, equals chunk size minus 0x4C", "Verified"],
  ["0x4C", "Tag body begins", "Verified"],
];

const inventory: Array<[string, string, string]> = [
  ["sound", "snd!", "5,895"],
  ["effect", "effe", "884"],
  ["skeleton_model", "skel", "460"],
  ["model", "hlmt", "451"],
  ["collision_model", "coll", "424"],
  ["physics_model", "phmo", "421"],
  ["squad_template", "sqtm", "343"],
  ["model_animation_graph", "jmad", "176"],
  ["character", "char", "132"],
  ["scenario_structure_bsp", "sbsp", "122"],
  ["weapon", "weap", "75"],
  ["projectile", "proj", "61"],
  ["biped", "bipd", "32"],
  ["vehicle", "vehi", "25"],
  ["scenario", "scnr", "13"],
  ["render_model", "mode", "0"],
  ["bitmap", "bitm", "0"],
];

const generated: Array<[string, string]> = [
  ["scenario_structure_bsp", "122"],
  ["scenario_structure_lighting_info", "122"],
  ["structure_design", "42"],
  ["scenario", "13"],
  ["structure_seams", "13"],
];

export default function TagDataPage() {
  return (
    <main className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-9">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <EvidenceBadge level="Verified" />
          <span className="text-xs text-text-dim">Build 2026.06.26.1097863.1, CU2</span>
        </div>
        <div className="flex items-start gap-4">
          <Package className="mt-1 h-7 w-7 shrink-0 text-gold" />
          <div>
            <h1 className="break-words text-3xl font-black sm:text-4xl">Blam tag data</h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-text-muted">
              Halo Campaign Evolved is not a Halo-themed Unreal game. It ships 12,328 genuine Blam
              tag files across 101 classic tag groups, wrapped one-per-Unreal-package. Rendering is
              fully Unreal: zero render_model tags and zero bitmap tags ship.
            </p>
          </div>
        </div>
      </header>

      <section className="py-9" aria-labelledby="split-heading">
        <div className="flex items-center gap-3">
          <Layers className="h-5 w-5 text-gold" />
          <h2 id="split-heading" className="text-xl font-bold">
            Simulation versus presentation
          </h2>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div className="border border-border bg-surface p-5">
            <h3 className="text-sm font-bold uppercase text-accent-green">Blam owns</h3>
            <p className="mt-3 text-sm leading-6 text-text-muted">
              Bipeds, weapons, vehicles, projectiles, equipment, AI characters, squads, styles,
              animation graphs, collision models, physics models, skeletons, damage effects, sound
              definitions, Megalo, and multiplayer variant settings.
            </p>
          </div>
          <div className="border border-border bg-surface p-5">
            <h3 className="text-sm font-bold uppercase text-accent-blue">Unreal owns</h3>
            <p className="mt-3 text-sm leading-6 text-text-muted">
              Every mesh, material, texture, world, and visual effect. Object definitions bind to
              Blueprint actors, so an Elite is a Blam biped tag driving BP_EliteBipedActor.
            </p>
          </div>
        </div>
        <p className="mt-5 text-sm leading-6 text-text-muted">
          The decisive check is the Elite model tag. It imports 16 packages and all 16 are Blam tags:
          collision model, physics model, skeleton model, animation graph, and shield effects. It
          references no mesh, no material, and no texture. The classic render chain was removed and
          replaced, while the simulation chain was kept intact.
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="packaging-heading">
        <h2 id="packaging-heading" className="text-xl font-bold">
          How tags are packaged
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          All 28 IoStore containers are UE 5.5 TOC version 8, Oodle compressed, indexed, and not
          encrypted. The directory index lists 132,091 entries. There are no loose tag files and no
          .map cache anywhere in the install.
        </p>
        <dl className="mt-5 grid border-y border-border text-sm sm:grid-cols-[220px_1fr]">
          <dt className="border-b border-border py-3 font-semibold text-text-muted sm:pr-5">
            Entries under Content/Tags
          </dt>
          <dd className="border-b border-border py-3 font-mono">24,618</dd>
          <dt className="border-b border-border py-3 font-semibold text-text-muted sm:pr-5">
            Tag packages
          </dt>
          <dd className="border-b border-border py-3 font-mono">12,328 (.uasset, 8.5 MiB)</dd>
          <dt className="border-b border-border py-3 font-semibold text-text-muted sm:pr-5">
            Tag payloads
          </dt>
          <dd className="border-b border-border py-3 font-mono">12,290 (.ubulk, 5,648.6 MiB)</dd>
          <dt className="py-3 font-semibold text-text-muted sm:pr-5">Distinct tag groups</dt>
          <dd className="py-3 font-mono">101</dd>
        </dl>
        <p className="mt-5 text-sm leading-6 text-text-muted">
          The Blam path objects\characters\elite\elite.biped becomes the Unreal package
          /Game/Tags/objects/characters/elite/elite-biped. The group separator changed from a dot to
          a hyphen because Unreal reserves the dot for object paths. The Unreal export is a thin
          104-byte header; the 49,702-byte tag body lives in the bulk-data segment.
        </p>
        <div className="mt-5 border-l-2 border-accent-green bg-surface px-5 py-4 font-mono text-xs leading-6 sm:text-sm">
          class = /Script/BlamSynchronization/BlamBipedTagDataAsset
        </div>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          BlamSynchronization declares 176 tag wrapper classes. 101 of them ship data. The render-side
          wrappers exist in the plugin but never ship instances.
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="format-heading">
        <h2 id="format-heading" className="text-xl font-bold">
          Tag container format
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          Verified across 168 sampled payloads covering all 101 shipped groups. Every payload begins
          with a 0x4C-byte header, and header plus payload size equals chunk size in every sample.
        </p>        <div className="mt-5 overflow-x-auto border border-border">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="bg-surface text-xs uppercase text-text-dim">
              <tr>
                <th className="px-4 py-3">Offset</th>
                <th className="px-4 py-3">Field</th>
                <th className="px-4 py-3">Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {headerFields.map(([offset, field, evidence]) => (
                <tr key={offset}>
                  <td className="px-4 py-3 font-mono text-gold">{offset}</td>
                  <td className="px-4 py-3 leading-6 text-text-muted">{field}</td>
                  <td className="px-4 py-3 text-xs uppercase text-text-dim">{evidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-5 text-sm leading-6 text-text-muted">
          The body past 0x4C is no longer opaque. Every tag carries a blay layout section describing
          its own fields, including the original Guerilla field and option names. See{" "}
          <Link href="/docs/research/tag-format" className="text-gold hover:underline">
            Self-describing tag layout
          </Link>
          .
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="inventory-heading">
        <div className="flex items-center gap-3">
          <Boxes className="h-5 w-5 text-gold" />
          <h2 id="inventory-heading" className="text-xl font-bold">
            Shipped inventory
          </h2>
        </div>
        <div className="mt-5 overflow-x-auto border border-border">
          <table className="w-full min-w-[460px] text-left text-sm">
            <thead className="bg-surface text-xs uppercase text-text-dim">
              <tr>
                <th className="px-4 py-3">Group</th>
                <th className="px-4 py-3">Four-CC</th>
                <th className="px-4 py-3 text-right">Tags</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {inventory.map(([group, code, count]) => (
                <tr key={group}>
                  <td className="px-4 py-3 font-mono text-text-muted">{group}</td>
                  <td className="px-4 py-3 font-mono text-gold">{code}</td>
                  <td className="px-4 py-3 text-right font-mono">{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="levels-heading">
        <h2 id="levels-heading" className="text-xl font-bold">
          Level pipeline
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          312 tags live under a _Generated_ directory, and they are exactly the world geometry
          groups. The 13 generated scenario tags map one-to-one onto the 13 root Halo worlds under
          /Game/Levels/Halo1/Solo.
        </p>
        <div className="mt-5 overflow-x-auto border border-border">
          <table className="w-full min-w-[420px] text-left text-sm">
            <thead className="bg-surface text-xs uppercase text-text-dim">
              <tr>
                <th className="px-4 py-3">Generated group</th>
                <th className="px-4 py-3 text-right">Count</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {generated.map(([group, count]) => (
                <tr key={group}>
                  <td className="px-4 py-3 font-mono text-text-muted">{group}</td>
                  <td className="px-4 py-3 text-right font-mono">{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-5 flex items-start gap-3 border border-gold/30 bg-gold/5 p-4">
          <EvidenceBadge level="Hypothesis" />
          <p className="text-sm leading-6 text-text-muted">
            Levels appear to be authored in Unreal, with the Blam scenario, BSP, seam, and
            soft-ceiling tags emitted from the Unreal world at cook time so the simulation gets its
            collision and structure representation. The _Generated_ directory name and the absence of
            any hand-authored scenario tag support this, but the cooker has not been observed.
          </p>
        </div>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="naming-heading">
        <h2 id="naming-heading" className="text-xl font-bold">
          Why the DLL is named tag_release
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          The host executable declares EBlamEngineBuildConfiguration with the members TagPlay,
          TagProfile, TagRelease, and TagTest. HaloSimulation_tag_release.dll is the TagRelease
          configuration. In classic Blam terminology a tag build consumes individual tag files rather
          than a compiled cache map, which matches the shipped data layout exactly.
        </p>
        <p className="mt-4 text-sm text-text-muted">
          Related:{" "}
          <Link href="/docs/research/halo-simulation" className="text-gold hover:underline">
            HaloSimulation_tag_release.dll
          </Link>
          .
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="multiplayer-heading">
        <h2 id="multiplayer-heading" className="text-xl font-bold">
          Multiplayer relevance
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          319 multiplayer tags ship, of which 308 sit under game_variant_settings. Multiplayer
          globals, the object type list, the game engine settings definition, team names, random
          player names, Megalo, and Sandbox are all present as readable tag data rather than loose
          strings.
        </p>
        <div className="mt-5 flex items-start gap-3 border border-border bg-surface p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-gold" />
          <p className="text-sm leading-6 text-text-muted">
            This does not prove a competitive mode is launchable. No multiplayer scenario tag and no
            competitive world package exists in this build, so a competitive map likely needs both an
            Unreal world and a matching generated Blam scenario and BSP set.
          </p>
        </div>
        <p className="mt-4 text-sm text-text-muted">
          Related:{" "}
          <Link href="/docs/research/multiplayer" className="text-gold hover:underline">
            Multiplayer viability
          </Link>
          .
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="reproduce-heading">
        <h2 id="reproduce-heading" className="text-xl font-bold">
          Reproduce
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          The tooling is read-only against your own installed copy. UE 5.5 and newer statically link
          Oodle, so the game ships no oo2core DLL; any oo2core_9_win64.dll from a local Unreal Engine
          install works.
        </p>
        <pre className="mt-5 overflow-x-auto border border-border bg-surface p-4 text-xs leading-6 text-text-muted">
          <code>{`# Container headers
python tools/iostore/dump_index.py --paks $paks --summary

# Full path index
python tools/iostore/dump_index.py --paks $paks --ext-stats --out out/iostore_paths.tsv

# Verify the BLAM header on one payload per tag group
python tools/iostore/inspect_tags.py --paks $paks --oodle $oodle --per-group 1

# Resolve the Unreal class that owns a tag package
python tools/iostore/zen_class.py --paks $paks --oodle $oodle \\
  --package "../../../Meteorite/Content/Tags/objects/Characters/Elite/elite-biped.uasset"`}</code>
        </pre>
        <p className="mt-4 text-sm text-text-muted">
          Tooling is checked in at{" "}
          <Link
            href="https://github.com/devnull9090/mjolnir-core/tree/main/tools/iostore"
            target="_blank"
            className="text-gold hover:underline"
          >
            tools/iostore
          </Link>
          . Extracted tag data is copyrighted game content. Keep it local and do not redistribute it.
        </p>
      </section>
    </main>
  );
}
