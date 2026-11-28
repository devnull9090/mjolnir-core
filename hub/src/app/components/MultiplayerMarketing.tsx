import Link from "next/link";
import { ArrowRight, ChevronDown, Download } from "lucide-react";
import { DiscordIcon } from "./icons";
import { Reveal } from "./Motion";
import { DISCORD_URL, MULTIPLAYER_FAQS, PLAY_STEPS } from "@/lib/marketing";

export function PlaySteps() {
  return (
    <ol className="grid gap-6 md:grid-cols-3 md:gap-8">
      {PLAY_STEPS.map((step, index) => (
        <li key={step.title} className="relative h-full">
          <Reveal delay={index * 45} className="h-full">
            <div className="group flex h-full flex-col rounded-xl border border-border bg-background/55 p-6 transition-all duration-200 hover:-translate-y-0.5 hover:border-gold/40">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-10 items-center justify-center rounded-lg border border-gold/40 bg-surface font-mono text-sm font-bold text-gold shadow-[0_0_20px_-6px_rgba(212,168,67,0.5)] transition-colors group-hover:bg-gold group-hover:text-background">
                  0{index + 1}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-dim">
                  Step {index + 1} of {PLAY_STEPS.length}
                </span>
              </div>
              <h3 className="mt-5 text-xl font-bold text-foreground">{step.title}</h3>
              <p className="mt-2.5 text-sm leading-7 text-text-muted">{step.description}</p>
            </div>
          </Reveal>
          {index < PLAY_STEPS.length - 1 && (
            <span
              aria-hidden="true"
              className="pointer-events-none hidden md:flex items-center justify-center absolute -right-6 top-9 size-4 text-gold/50"
            >
              <ArrowRight className="size-4" />
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

export function MultiplayerFaq({ compact = false }: { compact?: boolean }) {
  const faqs = compact ? MULTIPLAYER_FAQS.slice(0, 3) : MULTIPLAYER_FAQS;
  return (
    <div className="divide-y divide-border rounded-xl border border-border bg-surface/50 overflow-hidden">
      {faqs.map((faq, index) => (
        <details
          key={faq.id}
          id={faq.id}
          className="group scroll-mt-40 border-l-2 border-l-transparent transition-colors open:border-l-gold open:bg-surface-raised/50"
          open={index === 0}
        >
          <summary className="flex cursor-pointer list-none items-center justify-between gap-6 px-5 py-5 text-base font-semibold transition-colors hover:text-gold marker:content-none [&::-webkit-details-marker]:hidden sm:px-6">
            <span>{faq.question}</span>
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background/60 text-gold transition-all group-hover:border-gold/40 group-open:rotate-180 group-open:bg-gold/10">
              <ChevronDown aria-hidden="true" className="size-4" />
            </span>
          </summary>
          <div className="max-w-3xl px-5 pb-6 text-sm leading-7 text-text-muted sm:px-6">
            <p>{faq.answer}</p>
            <Link href={faq.href} className="mt-3.5 inline-flex items-center gap-2 font-semibold text-gold hover:underline">
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
    <section className="marketing-community relative overflow-hidden border-y border-gold/20 px-6 py-16 md:py-24">
      <div
        aria-hidden="true"
        className="mj-grid-bg pointer-events-none absolute inset-0 opacity-60 [mask-image:radial-gradient(ellipse_at_center,black_20%,transparent_80%)]"
      />
      <Reveal className="relative mx-auto flex max-w-6xl flex-col justify-between gap-8 lg:flex-row lg:items-center">
        <div className="max-w-xl">
          <p className="marketing-eyebrow">Built by the community. Played together.</p>
          <h2 className="mt-4 text-4xl font-black tracking-tight md:text-5xl">Your fireteam is out there.</h2>
          <p className="mt-5 leading-7 text-text-muted">
            Find players, share your next map, and help shape multiplayer in Campaign Evolved. Join us on Discord.
          </p>
        </div>
        <div className="flex shrink-0 flex-col gap-3 sm:flex-row lg:flex-col">
          <Link href={DISCORD_URL} className="marketing-button-primary">
            <DiscordIcon className="size-5" /> Join the community <ArrowRight aria-hidden="true" className="size-4" />
          </Link>
          <Link href="/download" className="marketing-button-secondary">
            <Download aria-hidden="true" className="size-4" /> Download MJOLNIR
          </Link>
        </div>
      </Reveal>
    </section>
  );
}
