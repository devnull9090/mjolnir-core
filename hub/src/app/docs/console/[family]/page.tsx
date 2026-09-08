import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Hash } from "lucide-react";
import { EvidenceBadge } from "../../_components/EvidenceBadge";
import {
  consoleForm,
  getConsoleBuild,
  getConsoleFamilies,
  getConsoleFamily,
  getConsoleFamilySummary,
  signatureText,
  type ConsoleFunction,
} from "@/lib/console";

type Params = { family: string };

export function generateStaticParams(): Params[] {
  return getConsoleFamilies().map((f) => ({ family: f.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { family: slug } = await params;
  const summary = getConsoleFamilySummary(slug);
  const family = getConsoleFamily(slug);
  if (!summary || !family)
    return { title: "Unknown console family | MJOLNIR Docs" };

  const names = family.functions
    .filter((f) => !f.stub)
    .slice(0, 6)
    .map((f) => f.name);
  const title = `${summary.title} console commands (${summary.count}) | MJOLNIR Docs`;
  const description =
    `${summary.count} ${summary.title} functions of the Halo Campaign Evolved Blam console, ` +
    `${summary.live} of them live in the release build` +
    (names.length > 0 ? `: ${names.join(", ")}` : "") +
    ". Signatures, return types and how the campaign scripts call them.";

  return {
    title,
    description,
    keywords: [
      `${summary.title} console commands`,
      "Halo Campaign Evolved",
      "Blam console",
      "HS script",
      "Halo modding",
      ...names.slice(0, 4),
    ],
    alternates: { canonical: `/docs/console/${slug}` },
    openGraph: { title, description, type: "article" },
  };
}

function Badge({
  children,
  tone = "dim",
}: {
  children: React.ReactNode;
  tone?: "dim" | "gold";
}) {
  const cls =
    tone === "gold"
      ? "border-gold/40 bg-gold/10 text-gold"
      : "border-border-bright bg-surface-raised text-text-muted";
  return (
    <span
      className={`inline-flex items-center border px-1.5 py-0.5 text-[10px] font-bold uppercase ${cls}`}
    >
      {children}
    </span>
  );
}

function UsageLine({ fn }: { fn: ConsoleFunction }) {
  if (!fn.usage) return null;
  const { calls, minArgs, maxArgs } = fn.usage;
  const args =
    minArgs === maxArgs
      ? `${minArgs} argument${minArgs === 1 ? "" : "s"}`
      : `${minArgs} to ${maxArgs} arguments`;
  return (
    <p className="mt-2 text-xs text-text-dim">
      Called {calls.toLocaleString()} time{calls === 1 ? "" : "s"} by the
      shipped campaign scripts, with {args}.
    </p>
  );
}

export default async function ConsoleFamilyPage({
  params,
}: {
  params: Promise<Params>;
}) {
  const { family: slug } = await params;
  const summary = getConsoleFamilySummary(slug);
  const family = getConsoleFamily(slug);
  if (!summary || !family) notFound();

  const build = getConsoleBuild();

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
          <Hash className="mt-1 h-7 w-7 shrink-0 text-gold" />
          <div className="min-w-0">
            <h1 className="break-words text-3xl font-black sm:text-4xl">
              {summary.title}
            </h1>
            {family.description && (
              <p className="mt-4 max-w-3xl text-base leading-7 text-text-muted">
                {family.description}
              </p>
            )}
          </div>
        </div>

        <dl className="mt-7 grid grid-cols-3 gap-px border border-border bg-border">
          {[
            ["Functions", summary.count.toLocaleString()],
            ["Work in this build", summary.live.toLocaleString()],
            ["Compiled out", summary.stubs.toLocaleString()],
          ].map(([label, value]) => (
            <div key={label} className="bg-background px-4 py-4">
              <dt className="text-xs uppercase text-text-dim">{label}</dt>
              <dd className="mt-1 font-mono text-base text-gold">{value}</dd>
            </div>
          ))}
        </dl>
      </header>

      <nav
        className="border-b border-border py-7"
        aria-labelledby="toc-heading"
      >
        <h2
          id="toc-heading"
          className="text-xs font-bold uppercase text-text-dim"
        >
          {summary.count} names
        </h2>
        <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-2">
          {family.functions.map((fn) => (
            <li key={`toc-${fn.anchor}`}>
              <a
                href={`#${fn.anchor}`}
                className={`break-all font-mono text-xs hover:text-gold ${
                  fn.stub
                    ? "text-text-dim line-through decoration-border-bright"
                    : "text-text-muted"
                }`}
              >
                {fn.name}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {family.functions.map((fn) => (
        <section
          key={fn.anchor}
          id={fn.anchor}
          className="scroll-mt-24 border-b border-border py-7"
          aria-labelledby={`${fn.anchor}-heading`}
        >
          <div className="flex flex-wrap items-center gap-3">
            <h2
              id={`${fn.anchor}-heading`}
              className="break-all font-mono text-lg font-bold"
            >
              {fn.name}
            </h2>
            {fn.stub && <Badge>compiled out</Badge>}
            {fn.signatures.some((s) => s.special) && (
              <Badge tone="gold">special form</Badge>
            )}
            {fn.signatures.length > 1 && (
              <Badge>{fn.signatures.length} overloads</Badge>
            )}
            {fn.returns.filter((r) => r !== "void" && r !== "passthrough")
              .length > 0 && (
              <span className="font-mono text-xs text-text-dim">
                →{" "}
                {fn.returns
                  .filter((r) => r !== "void" && r !== "passthrough")
                  .join(" | ")}
              </span>
            )}
          </div>

          {fn.description ? (
            <p className="mt-3 text-sm leading-6 text-text-muted">
              {fn.description}
            </p>
          ) : (
            <p className="mt-3 text-sm leading-6 text-text-dim">
              No description yet; the release build dropped the engine&apos;s
              help text.
            </p>
          )}

          <div className="mt-4 overflow-x-auto border border-border bg-surface">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="text-xs uppercase text-text-dim">
                <tr>
                  <th className="px-4 py-2">Signature</th>
                  <th className="px-4 py-2">Returns</th>
                  <th className="px-4 py-2 text-right">Slot</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {fn.signatures.map((sig) => (
                  <tr
                    key={sig.index}
                    className={sig.stub ? "text-text-dim" : ""}
                  >
                    <td className="px-4 py-2 font-mono text-xs">
                      {signatureText(fn.name, sig)}
                      {sig.stub && !fn.stub && (
                        <span className="ml-2 text-[10px] uppercase">
                          compiled out
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-gold">
                      {sig.returns}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-text-dim">
                      {sig.index}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!fn.stub && (
            <p className="mt-3 font-mono text-xs text-text-muted">
              <span className="text-text-dim">console: </span>
              {consoleForm(
                fn.name,
                fn.signatures.find((s) => !s.stub) ?? fn.signatures[0],
              )}
            </p>
          )}
          <UsageLine fn={fn} />
        </section>
      ))}

      <section className="py-9">
        <p className="text-sm leading-6 text-text-muted">
          Read from the function table in the shipped simulation DLL. A name is
          compiled out when every one of its slots points at the release
          build&apos;s shared stub evaluator; the console still accepts it and
          returns nothing. Descriptions are hand-written and incomplete; the
          engine&apos;s own help text does not survive in this build. See{" "}
          <Link
            href="/docs/notes/blam-console"
            className="text-gold hover:underline"
          >
            The Blam console
          </Link>{" "}
          for how the table was found and how the mod runs these.
        </p>
      </section>
    </main>
  );
}
