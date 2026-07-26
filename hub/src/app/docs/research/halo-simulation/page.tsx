import type { Metadata } from "next";
import Link from "next/link";
import { AlertTriangle, Binary, GitBranch } from "lucide-react";
import { EvidenceBadge } from "../../_components/EvidenceBadge";

export const metadata: Metadata = {
  title: "HaloSimulation_tag_release.dll | MJOLNIR Docs",
  description:
    "Reverse-engineering notes for the HaloSimulation shell factory, object layout, interfaces, and UE5 loader path.",
};

const primarySlots = [
  ["0", "0x7230", "Releases the global shell allocation and clears shell state."],
  ["1", "0x7280", "Performs one-time initialization and normalizes a caller-supplied path."],
  ["2", "0x7360", "Large startup path: initializes tag systems and can create a worker thread."],
  ["3", "0x89F0", "Clears queues, frees worker state, waits for the worker, and closes its handle."],
  ["4", "0x6940", "Returns the embedded interface at this + 0x140."],
  ["5", "0x8B00", "Builds an auxiliary result/container; semantic role is not yet identified."],
  ["6", "0x9A00", "Allocates and returns an auxiliary callback object."],
  ["7", "0x9A70", "Releases four callback/object references."],
  ["8", "0x6130", "Control Flow Guard placeholder in the recovered table."],
];

export default function HaloSimulationPage() {
  return (
    <main className="mx-auto max-w-4xl">
      <header className="border-b border-border pb-9">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <EvidenceBadge level="Verified" />
          <span className="text-xs text-text-dim">Build 2026.06.26.1097863.1, CU2</span>
        </div>
        <div className="flex items-start gap-4">
          <Binary className="mt-1 h-7 w-7 shrink-0 text-gold" />
          <div>
            <h1 className="break-words text-3xl font-black sm:text-4xl">
              HaloSimulation_tag_release.dll
            </h1>
            <p className="mt-4 max-w-3xl text-base leading-7 text-text-muted">
              Native Blam simulation module loaded by the UE5 BlamEngine plugin. This page records
              the current factory ABI and interface shape recovered from the installed CU2 build.
            </p>
          </div>
        </div>
      </header>

      <section className="py-9" aria-labelledby="fingerprint-heading">
        <h2 id="fingerprint-heading" className="text-xl font-bold">
          Artifact fingerprint
        </h2>
        <dl className="mt-5 grid border-y border-border text-sm sm:grid-cols-[150px_1fr]">
          <dt className="border-b border-border py-3 font-semibold text-text-muted sm:pr-5">Size</dt>
          <dd className="break-all border-b border-border py-3 font-mono">14,670,608 bytes</dd>
          <dt className="border-b border-border py-3 font-semibold text-text-muted sm:pr-5">SHA-256</dt>
          <dd className="break-all border-b border-border py-3 font-mono text-xs">
            8EE1A37F6F0BC89241F47946546EDCA798962F81E2D06B386196BC75DE991705
          </dd>
          <dt className="py-3 font-semibold text-text-muted sm:pr-5">Image base</dt>
          <dd className="py-3 font-mono">0x180000000</dd>
        </dl>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="factory-heading">
        <div className="flex items-center gap-3">
          <GitBranch className="h-5 w-5 text-gold" />
          <h2 id="factory-heading" className="text-xl font-bold">
            Shell factory
          </h2>
        </div>
        <div className="mt-5 border-l-2 border-accent-green bg-surface px-5 py-4 font-mono text-sm">
          bool CreateBlamEngineShell(void* context, void** outShell)
        </div>
        <ul className="mt-5 space-y-3 text-sm leading-6 text-text-muted">
          <li>Export RVA: 0x6980.</li>
          <li>Allocates 0x5A0 bytes aligned to 0x20 bytes.</li>
          <li>Installs interface tables at object offsets 0x0 and 0x140.</li>
          <li>Initializes three lock-free lists and a 32-entry reusable event pool.</li>
          <li>Replaces the process-global shell, frees the previous allocation, writes outShell, and returns 1.</li>
        </ul>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="interface-heading">
        <h2 id="interface-heading" className="text-xl font-bold">
          Primary interface
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          The table at RVA 0x7B1560 has nine entries. Names below describe observed behavior; they
          are not recovered source symbols.
        </p>
        <div className="mt-5 overflow-x-auto border border-border">
          <table className="w-full min-w-[620px] text-left text-sm">
            <thead className="bg-surface text-xs uppercase text-text-dim">
              <tr>
                <th className="px-4 py-3">Slot</th>
                <th className="px-4 py-3">RVA</th>
                <th className="px-4 py-3">Observed behavior</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {primarySlots.map(([slot, rva, behavior]) => (
                <tr key={slot}>
                  <td className="px-4 py-3 font-mono text-gold">{slot}</td>
                  <td className="px-4 py-3 font-mono">{rva}</td>
                  <td className="px-4 py-3 leading-6 text-text-muted">{behavior}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="output-heading">
        <h2 id="output-heading" className="text-xl font-bold">
          Embedded output interface
        </h2>
        <p className="mt-3 text-sm leading-6 text-text-muted">
          Slot 4 returns <span className="font-mono text-foreground">this + 0x140</span>, whose
          table is at RVA 0x7B1610. It also has nine entries. One method drains and dispatches shell
          events, four methods enqueue typed payloads through the lock-free pool, and three small
          thunks release payload objects.
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="loader-heading">
        <h2 id="loader-heading" className="text-xl font-bold">
          UE5 loader path
        </h2>
        <div className="mt-5 space-y-4 text-sm leading-6 text-text-muted">
          <p>
            The matching host is CU2 build 2026.06.26.1097863.1. Its SHA-256 is
            0670FAA751E2553940B90DF6BE43D3B0FF59EA87F22155CF3C3FE9D439367F1D.
          </p>
          <ol className="list-decimal space-y-2 pl-5">
            <li>A launcher method constructs the wide module basename HaloSimulation.</li>
            <li>The engine module loader stores its handle at launcher offset 0x1A0.</li>
            <li>The export resolver looks up CreateBlamEngineShell.</li>
            <li>The factory writes the shell pointer at launcher offset 0x1C8.</li>
            <li>UE5 immediately invokes primary interface slot 1.</li>
          </ol>
          <p>
            The host does not contain a contiguous tag_release filename. That suffix is selected
            below this recovered launcher layer.
          </p>
        </div>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="limits-heading">
        <div className="flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-gold" />
          <h2 id="limits-heading" className="text-xl font-bold">
            Current limits
          </h2>
        </div>
        <p className="mt-4 text-sm leading-6 text-text-muted">
          Slot names remain behavioral labels, not source symbols. Runtime invocation has not yet
          established which startup structures select CTF or another game variant. The next useful
          step is to trace host call sites for primary slots 2 and 3, then correlate their inputs
          with the reflected BlamGameEngineBaseVariant and BlamGameEngineCampaignVariant objects.
        </p>
      </section>

      <section className="border-t border-border py-9" aria-labelledby="reproduce-heading">
        <h2 id="reproduce-heading" className="text-xl font-bold">
          Reproduce
        </h2>
        <pre className="mt-5 overflow-x-auto border border-border bg-surface p-4 text-xs leading-6 text-text-muted">
          <code>{`analyzeHeadless <project-dir> HaloSimulation \\
  -import HaloSimulation_tag_release.dll \\
  -scriptPath tools/ghidra \\
  -postScript AnalyzeBlamShell.java <output-dir>`}</code>
        </pre>
        <p className="mt-4 text-sm text-text-muted">
          The reusable probe is checked in at{" "}
          <Link
            href="https://github.com/devnull9090/mjolnir-core/blob/main/tools/ghidra/AnalyzeBlamShell.java"
            target="_blank"
            className="text-gold hover:underline"
          >
            tools/ghidra/AnalyzeBlamShell.java
          </Link>
          .
        </p>
      </section>
    </main>
  );
}