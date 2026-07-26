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
  ["0x00", "4", "blay four-CC, stored as the bytes y a l b", "Verified"],
  ["0x04", "4", "Section version, 2 in all 101 groups", "Verified"],
  ["0x08", "4", "Section size, measured from body 0x00", "Verified"],
  ["0x0C", "4", "0xFFFFFFFF", "Verified"],
  ["0x10", "12", "Fixed ASCII fill: 4444, CCCC, wwww", "Verified"],
  ["0x1C", "4", "Per-group constant", "Observed"],
  ["0x20", "56", "Count and size table, uninterpreted", "Observed"],
  ["0x58", "12", "tgly container section header", "Verified"],
  ["0x64", "12", "str* string blob section header", "Verified"],
  ["0x70", "n", "NUL-separated UTF-8 string blob", "Verified"],
  ["blob end", "12", "x+zs marker, zero word, option count", "Verified"],
  ["+0x0C", "4n", "String offsets, one per enum or bitfield option", "Observed"],
  ["after", "n", "Field definition records", "Observed"],
];

const blobSizes: Array<[string, string, string, string]> = [
  ["character", "char", "1,038", "1,248"],
  ["biped", "bipd", "1,031", "1,688"],
  ["chud_definition", "chdt", "899", "2,447"],
  ["weapon", "weap", "783", "1,312"],
  ["collision_model", "coll", "270", "120"],
  ["camera_track", "trak", "10", "0"],
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
          Section layout
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          Offsets are relative to the start of the tag body, which begins at file offset 0x4C. The
          section is byte-packed throughout, so the option table routinely starts on an unaligned
          offset. Do not assume dword alignment.
        </p>
        <div className="mt-5 overflow-x-auto border border-border">
          <table className="w-full min-w-[620px] text-left text-sm">
            <thead className="bg-surface text-xs uppercase text-text-dim">
              <tr>
                <th className="px-4 py-3">Offset</th>
                <th className="px-4 py-3">Size</th>
                <th className="px-4 py-3">Field</th>
                <th className="px-4 py-3">Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sections.map(([offset, size, field, evidence]) => (
                <tr key={offset + field}>
                  <td className="px-4 py-3 font-mono text-gold">{offset}</td>
                  <td className="px-4 py-3 font-mono text-text-dim">{size}</td>
                  <td className="px-4 py-3 leading-6 text-text-muted">{field}</td>
                  <td className="px-4 py-3 text-xs uppercase text-text-dim">{evidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-5 text-sm leading-6 text-text-muted">
          Strings are referenced by byte offset into the blob rather than by index. The 4444, CCCC,
          and wwww dwords previously recorded as uninterpreted markers are fixed ASCII fill inside
          the blay header.
        </p>
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
                <th className="px-4 py-3 text-right">Options</th>
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
              <p className="text-sm font-semibold">Field records are variable-length</p>
              <p className="mt-2 text-sm leading-6 text-text-muted">
                Records begin with a name offset, a type code, and an auxiliary word. Reading at a
                fixed 12-byte stride is correct at the start of the table but desynchronizes partway
                through: later names resolve to byte-shifted substrings such as ong flags for long
                flags. Certain type codes almost certainly carry trailing inline payload.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3 border border-border bg-surface p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-gold" />
            <div>
              <p className="text-sm font-semibold">Option table overruns in 16 of 101 groups</p>
              <p className="mt-2 text-sm leading-6 text-text-muted">
                chud_definition declares 2,964 option entries, which would end 4,908 bytes past its
                own layout section. The reader flags the condition rather than guessing at it.
              </p>
            </div>
          </div>
        </div>
        <p className="mt-5 text-sm leading-6 text-text-muted">
          Neither blocks reading tag structure, and both are isolated to the field table. The
          decisive test for the record encoding is that every name offset must land on a string blob
          boundary across all 101 groups.
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
          5.5 IoStore containers, blam-tag parses the container header and layout section, blam-defs
          holds the shared definition model, and blam-cli exposes it as the mjolnir command. It
          parses 101 of 101 groups across all 12,290 shipped payloads.
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

# Every group, with layout sizes and coverage
cargo run --release -p blam-cli -- groups

# One group's strings, options, and field records
cargo run --release -p blam-cli -- layout --group weapon --options

# Field type code histogram across all groups
cargo run --release -p blam-cli -- type-codes

# Python explorer used to find the format
python tools/iostore/decode_body.py --paks $env:HCE_PAKS --oodle $env:OODLE --survey`}</code>
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
