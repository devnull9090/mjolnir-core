import type { Metadata } from "next";
import Link from "next/link";
import { AlertTriangle, Braces, FileCode, Layers, Terminal } from "lucide-react";
import { EvidenceBadge } from "../../_components/EvidenceBadge";

export const metadata: Metadata = {
  title: "Self-describing tag layout | MJOLNIR Docs",
  description:
    "Halo Campaign Evolved tag files carry their own field definitions. The blay layout section ships real Guerilla field names, type names, and enum options for all 101 tag groups.",
};

const sections: Array<[string, string, string, string]> = [
  ["blay", "layout", "The tag's own field definitions", "Verified"],
  ["tgly", "container", "Holds every definition table", "Verified"],
  ["str*", "blob", "NUL-separated UTF-8 strings, referenced by byte offset", "Verified"],
  ["options", "table", "String offsets, one per enum or bitfield option", "Verified"],
  ["tgft", "table", "Types: name, on-disk size, composite flag", "Verified"],
  ["gras", "table", "Fields: name, type index", "Verified"],
  ["blv2", "table", "Blocks: name, maximum element count", "Verified"],
  ["stv4", "table", "Structs: 16-byte GUID and name", "Verified"],
  ["bdat", "data", "The tag's actual field values", "Verified"],
  ["tgbl", "container", "Wraps the data payload", "Verified"],
];

const blobSizes: Array<[string, string, string, string]> = [
  ["character", "char", "1,038", "1,248"],
  ["biped", "bipd", "1,031", "582"],
  ["weapon", "weap", "783", "503"],
  ["chud_definition", "chdt", "899", "612"],
  ["collision_model", "coll", "270", "388"],
  ["camera_track", "trak", "10", "5"],
];

export default function TagFormatPage() {
  return (
    <main className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-9">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <EvidenceBadge level="Verified" />
          <span className="text-xs text-text-dim">Build 2026.06.26.1097863.1, CU2</span>
        </div>
        <div className="flex items-start gap-4">
          <Braces className="mt-1 h-7 w-7 shrink-0 text-gold" />
          <div>
            <h1 className="break-words text-3xl font-black sm:text-4xl">
              Tag files describe themselves
            </h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-text-muted">
              Every shipped tag carries a blay layout section holding its own field names, type
              names, and enum option names. The definitions for all 101 tag groups are recoverable
              from the shipped data alone, without touching the engine binary.
            </p>
          </div>
        </div>
      </header>

      <section className="py-9" aria-labelledby="why-heading">
        <div className="flex items-center gap-3">
          <Layers className="h-5 w-5 text-gold" />
          <h2 id="why-heading" className="text-xl font-bold">
            Why this matters
          </h2>
        </div>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          The expected route to a tag editor was recovering field definitions from
          HaloSimulation_tag_release.dll, since Blam tag builds historically embed their definition
          tables. That work is no longer on the critical path. The strings below came out of a
          shipped weapon tag, and they are the same human-readable names Guerilla displayed:
        </p>
        <div className="mt-5 border-l-2 border-accent-green bg-surface px-5 py-4 font-mono text-xs leading-6 sm:text-sm">
          <div className="text-text-muted">object flags</div>
          <div className="text-text-muted">long flags</div>
          <div className="text-text-muted">does not cast shadow</div>
          <div className="text-text-muted">search cardinal direction lightmaps on failure</div>
          <div className="text-text-muted">rounds total maximum</div>
          <div className="text-text-muted">early mover localized physics</div>
        </div>
        <p className="mt-5 text-sm leading-6 text-text-muted">
          Because each tag carries its own layout, a reader can be entirely generic. No hand-written
          per-group parsers and no hardcoded offsets are required, which is the failure mode that
          makes most Halo tag tooling brittle across builds.
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="layout-heading">
        <h2 id="layout-heading" className="text-xl font-bold">
          One shape, all the way down
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          The entire tag body is built from a single repeating shape: a 12-byte header of a
          four-CC magic, a version, and a content size, followed by that many bytes of content.
          The size excludes the header. Sections chain as siblings and nest as children at every
          level, so one generic walker reads the whole file.
        </p>
        <div className="mt-5 overflow-x-auto border border-border">
          <table className="w-full min-w-[620px] text-left text-sm">
            <thead className="bg-surface text-xs uppercase text-text-dim">
              <tr>
                <th className="px-4 py-3">Section</th>
                <th className="px-4 py-3">Kind</th>
                <th className="px-4 py-3">Contents</th>
                <th className="px-4 py-3">Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sections.map(([magic, kind, field, evidence]) => (
                <tr key={magic}>
                  <td className="px-4 py-3 font-mono text-gold">{magic}</td>
                  <td className="px-4 py-3 font-mono text-text-dim">{kind}</td>
                  <td className="px-4 py-3 leading-6 text-text-muted">{field}</td>
                  <td className="px-4 py-3 text-xs uppercase text-text-dim">{evidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-5 text-sm leading-6 text-text-muted">
          Strings are referenced by byte offset into the blob rather than by index, and an offset
          pointing at a NUL resolves to the empty string, which the data uses for unnamed fields
          such as padding. The blob is byte-packed, so nothing is reliably dword aligned.
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="worked-heading">
        <h2 id="worked-heading" className="text-xl font-bold">
          A group decoded end to end
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          camera_track is the smallest group and decodes completely. This is the real Halo
          definition, including the engine&apos;s actual 16 control-point limit. Terminator fields
          delimit struct boundaries, so the field list is a flattened tree rather than a nested
          one.
        </p>
        <pre className="mt-5 overflow-x-auto border border-border bg-surface p-4 text-xs leading-6 text-text-muted">
          <code>{`types:  [0] block            12b  composite
        [1] real vector 3d   12b
        [2] real quaternion  16b
        [3] terminator X      0b

fields: +0   12b  real vector 3d   position
        +12  16b  real quaternion  orientation
        +28   0b  terminator X     <unnamed>
        +28  12b  block            control points
        +40   0b  terminator X     <unnamed>

blocks: camera_track_control_point_block  max 16
        camera_track_block                max 1`}</code>
        </pre>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="sizes-heading">
        <h2 id="sizes-heading" className="text-xl font-bold">
          Definition size by group
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          All 101 groups parse. Groups with no enums or bitfields carry an empty option table.
        </p>
        <div className="mt-5 overflow-x-auto border border-border">
          <table className="w-full min-w-[480px] text-left text-sm">
            <thead className="bg-surface text-xs uppercase text-text-dim">
              <tr>
                <th className="px-4 py-3">Group</th>
                <th className="px-4 py-3">Four-CC</th>
                <th className="px-4 py-3 text-right">Strings</th>
                <th className="px-4 py-3 text-right">Fields</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {blobSizes.map(([group, code, strings, options]) => (
                <tr key={group}>
                  <td className="px-4 py-3 font-mono text-text-muted">{group}</td>
                  <td className="px-4 py-3 font-mono text-gold">{code}</td>
                  <td className="px-4 py-3 text-right font-mono">{strings}</td>
                  <td className="px-4 py-3 text-right font-mono">{options}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="open-heading">
        <h2 id="open-heading" className="text-xl font-bold">
          What is not solved yet
        </h2>
        <div className="mt-5 space-y-4">
          <div className="flex items-start gap-3 border border-gold/30 bg-gold/5 p-4">
            <EvidenceBadge level="Hypothesis" />
            <div>
              <p className="text-sm font-semibold">Zero-size types carry payload elsewhere</p>
              <p className="mt-2 text-sm leading-6 text-text-muted">
                Five types report a size of zero: array, custom, pad, struct, and terminator. Pad
                in particular must consume bytes, so the field record&apos;s auxiliary word is
                presumed to carry the length, the struct target, and the option run an enum or
                bitfield owns. That mapping is not yet established.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3 border border-border bg-surface p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-gold" />
            <div>
              <p className="text-sm font-semibold">The data walk is not yet proven</p>
              <p className="mt-2 text-sm leading-6 text-text-muted">
                The decisive test is walking the bdat payload with the field list and asserting it
                is consumed exactly, for all 12,290 shipped tags. Until that passes, field offsets
                into the data are inferred rather than confirmed.
              </p>
            </div>
          </div>
        </div>
        <p className="mt-5 text-sm leading-6 text-text-muted">
          A previous revision of this page reported that the option table overran its own section
          in 16 of 101 groups. That was a misreading: the word in question is a byte size, not an
          entry count. Read correctly, no group overruns.
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="tooling-heading">
        <div className="flex items-center gap-3">
          <FileCode className="h-5 w-5 text-gold" />
          <h2 id="tooling-heading" className="text-xl font-bold">
            Tooling
          </h2>
        </div>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          A Rust workspace under crates/ reads containers and layouts directly. ue-iostore parses UE
          5.5 IoStore containers, blam-tag parses the container header and section tree, blam-defs
          holds the shared definition model, and blam-cli exposes it as the mjolnir command. It
          parses 101 of 101 groups across all 12,290 shipped payloads and recovers a complete field
          list for every one.
        </p>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          54 distinct field type names appear across the corpus, and every one has the same size in
          every group it appears in. That consistency is the strongest available check that the type
          table decode is correct.
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="reproduce-heading">
        <div className="flex items-center gap-3">
          <Terminal className="h-5 w-5 text-gold" />
          <h2 id="reproduce-heading" className="text-xl font-bold">
            Reproduce
          </h2>
        </div>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          Read-only against your own installed copy. Any oo2core_9_win64.dll from a local Unreal
          Engine install works, since UE 5.5 statically links Oodle and the game ships no separate
          DLL. Nothing is written to disk.
        </p>
        <pre className="mt-5 overflow-x-auto border border-border bg-surface p-4 text-xs leading-6 text-text-muted">
          <code>{`$env:HCE_PAKS = "<install>\\Meteorite\\Content\\Paks"
$env:OODLE    = "<UE>\\Engine\\Binaries\\DotNET\\AutomationTool\\oo2core_9_win64.dll"

# Every group, with its definition table sizes
cargo run --release -p blam-cli -- groups

# One group's section tree and type, block, and struct tables
cargo run --release -p blam-cli -- layout --group camera_track --tables

# A group's resolved field list with running offsets
cargo run --release -p blam-cli -- fields --group weapon

# The field type vocabulary and its sizes
cargo run --release -p blam-cli -- types`}</code>
        </pre>
        <p className="mt-5 text-sm text-text-muted">
          Full working notes:{" "}
          <Link href="/docs/notes/tag-body-format" className="text-gold hover:underline">
            tag_body_format.md
          </Link>
          . Container and packaging detail:{" "}
          <Link href="/docs/research/tag-data" className="text-gold hover:underline">
            Blam tag data
          </Link>
          .
        </p>
      </section>
    </main>
  );
}
