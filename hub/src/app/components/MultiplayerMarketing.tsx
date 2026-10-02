import Link from "next/link";
import { ArrowRight, ChevronDown, Download } from "lucide-react";
import { DiscordIcon } from "./icons";
import { DISCORD_URL, MULTIPLAYER_FAQS, PLAY_STEPS } from "@/lib/marketing";

export function PlaySteps() {
  return (
    <ol className="grid gap-8 md:grid-cols-3">
      {PLAY_STEPS.map((step, index) => (
        <li key={step.title} className="border-t border-border-bright pt-6">
          <span className="font-mono text-sm text-gold">0{index + 1}</span>
          <h3 className="mt-4 text-xl font-bold">{step.title}</h3>
          <p className="mt-3 text-sm leading-7 text-text-muted">{step.description}</p>
        </li>
      ))}
    </ol>
  );
}

export function MultiplayerFaq({ compact = false }: { compact?: boolean }) {
  const faqs = compact ? MULTIPLAYER_FAQS.slice(0, 3) : MULTIPLAYER_FAQS;
  return (
    <div className="divide-y divide-border border-y border-border">
      {faqs.map((faq, index) => (
        <details key={faq.id} id={faq.id} className="group scroll-mt-40" open={index === 0}>
          <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-6 text-base font-semibold marker:content-none [&::-webkit-details-marker]:hidden">
            {faq.question}
            <ChevronDown aria-hidden="true" className="size-5 shrink-0 text-gold transition-transform group-open:rotate-180" />
          </summary>
          <div className="max-w-3xl pb-7 text-sm leading-7 text-text-muted">
            <p>{faq.answer}</p>
            <Link href={faq.href} className="mt-3 inline-flex items-center gap-2 font-medium text-gold hover:underline">
              {faq.linkLabel} <ArrowRight aria-hidden="true" className="size-4" />
            </Link>
          </div>
        </details>
      ))}
    </div>
  );
}

export function CommunityCallout() {
  return (
    <section className="marketing-community border-y border-gold/20 px-6 py-16 md:py-24">
      <div className="mx-auto flex max-w-6xl flex-col justify-between gap-8 lg:flex-row lg:items-center">
        <div className="max-w-xl">
          <p className="marketing-eyebrow">Built by the community. Played together.</p>
          <h2 className="mt-4 text-4xl font-black tracking-tight md:text-5xl">Your fireteam is out there.</h2>
          <p className="mt-5 leading-7 text-text-muted">Find players, share your next map, and help shape multiplayer in Campaign Evolved. Join us on Discord.</p>
        </div>
        <div className="flex shrink-0 flex-col gap-3">
          <Link href={DISCORD_URL} className="marketing-button-primary">
            <DiscordIcon className="size-5" /> Join the community <ArrowRight aria-hidden="true" className="size-4" />
          </Link>
          <Link href="/download" className="marketing-button-secondary">
            <Download aria-hidden="true" className="size-4" /> Download MJOLNIR
          </Link>
        </div>
      </div>
    </section>
  );
}
