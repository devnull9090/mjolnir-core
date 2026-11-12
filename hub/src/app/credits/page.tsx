import type { Metadata } from "next";
import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { PageHeader, PageShell, Pill, SectionHeading } from "../components/ui";
import { CREDIT_SECTIONS, type Credit } from "@/lib/credits";

const description =
  "The asset packs, software and tools MJOLNIR Core ships, builds with and learned from, with their makers and licences.";

export const metadata: Metadata = {
  title: "Credits | MJOLNIR Core",
  description,
  alternates: { canonical: "https://mjolnircore.com/credits" },
};

function CreditCard({ credit }: { credit: Credit }) {
  return (
    <li className="rounded-xl border border-border bg-surface-raised p-5">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h3 className="text-base font-bold text-foreground break-words">
            <Link
              href={credit.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 hover:text-gold transition-colors"
            >
              {credit.name}
              <ExternalLink aria-hidden className="w-3.5 h-3.5 shrink-0 text-text-dim" />
            </Link>
          </h3>
          <p className="text-sm text-text-muted">by {credit.by}</p>
        </div>
        {credit.status === "planned" && <Pill tone="gold">Not in a release yet</Pill>}
      </div>
      <p className="mt-3 text-sm leading-6 text-text-muted">{credit.use}</p>
      {credit.changes && (
        <p className="mt-2 text-sm leading-6 text-text-dim">
          <span className="font-semibold text-text-muted">Changes: </span>
          {credit.changes}
        </p>
      )}
      {credit.derived && (
        <p className="mt-2 text-sm leading-6">
          <Link
            href={credit.derived.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-gold hover:underline break-words"
          >
            {credit.derived.label}
          </Link>
        </p>
      )}
      <p className="mt-3 text-xs text-text-dim">
        <span className="font-semibold text-text-muted">Licence: </span>
        {credit.licenceUrl ? (
          <Link
            href={credit.licenceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="underline decoration-border-bright underline-offset-2 hover:text-foreground"
          >
            {credit.licence}
          </Link>
        ) : (
          credit.licence
        )}
      </p>
    </li>
  );
}

export default function CreditsPage() {
  return (
    <PageShell width="4xl">
      <PageHeader
        eyebrow="Credits"
        title="Built on other people's work"
        description="MJOLNIR Core stands on art, software and tools made by others. This is who they are, what we use, and the terms they share it under."
      />

      <nav aria-label="Sections" className="mb-10 flex flex-wrap gap-2">
        {CREDIT_SECTIONS.map((section) => (
          <Link
            key={section.id}
            href={`#${section.id}`}
            className="rounded-full border border-border-bright px-3 py-1.5 text-sm text-text-muted hover:border-gold/40 hover:text-foreground transition-colors"
          >
            {section.title}
          </Link>
        ))}
      </nav>

      {CREDIT_SECTIONS.map((section) => (
        <section key={section.id} className="mb-12 scroll-mt-28" id={section.id}>
          <SectionHeading>{section.title}</SectionHeading>
          <p className="mb-5 max-w-3xl text-sm leading-6 text-text-muted">{section.blurb}</p>
          <ul className="grid gap-4 sm:grid-cols-2">
            {section.entries.map((credit) => (
              <CreditCard key={credit.name} credit={credit} />
            ))}
          </ul>
        </section>
      ))}

      <section className="mb-12 scroll-mt-28" id="halo">
        <SectionHeading>Halo</SectionHeading>
        <div className="max-w-3xl space-y-3 text-sm leading-6 text-text-muted">
          <p>
            Halo Campaign Evolved, Halo: Combat Evolved, Halo 2 and everything in them belong to Microsoft and
            Halo Studios. The classic maps were made by Bungie. MJOLNIR Core is a community project: it is not
            affiliated with or endorsed by any of them, and you need your own copy of the games.
          </p>
          <p>
            Maps and mods on the Hub are credited to the people who published them, on each one&apos;s own page.
          </p>
        </div>
      </section>

      <section className="scroll-mt-28" id="missing">
        <SectionHeading>Something missing or wrong?</SectionHeading>
        <p className="max-w-3xl text-sm leading-6 text-text-muted">
          If we use your work and you are not here, or a licence is stated wrongly,{" "}
          <Link
            href="https://github.com/devnull9090/mjolnir-core/issues"
            target="_blank"
            rel="noopener noreferrer"
            className="text-gold hover:underline"
          >
            open an issue
          </Link>{" "}
          or tell us on{" "}
          <Link
            href="https://discord.gg/9gxYZsByW9"
            target="_blank"
            rel="noopener noreferrer"
            className="text-gold hover:underline"
          >
            Discord
          </Link>{" "}
          and we will fix it.
        </p>
      </section>
    </PageShell>
  );
}
