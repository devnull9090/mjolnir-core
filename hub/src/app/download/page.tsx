import Link from "next/link";
import {
  ArrowRight,
  CheckCircle,
  Cpu,
  Download,
  ExternalLink,
  Gamepad2,
  HardDrive,
  Monitor,
  Shield,
  Terminal,
  Wrench,
} from "lucide-react";

import { PageShell } from "../components/ui";
import { GitHubIcon } from "../components/icons";
import { Reveal, SpotlightCard } from "../components/Motion";
import { PlaySteps } from "../components/MultiplayerMarketing";
import ChecksumViewer from "./ChecksumViewer";
import { CliInstallTabs, CopyCommand } from "./CopyCommand";
import { marketingMetadata } from "@/lib/marketing";

export const metadata = marketingMetadata(
  "Download the Campaign Evolved Multiplayer Launcher | MJOLNIR",
  "Get MJOLNIR for Halo Campaign Evolved multiplayer. Install all 19 classic Halo CE maps, Slayer, CTF, mods, and creator tools from one Windows launcher.",
  "/download",
);

export default function DownloadPage() {
  return (
    <PageShell width="4xl" className="marketing">
      {/* Header */}
      <header className="relative mb-12 text-center">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-24 left-1/2 -z-10 h-64 w-[36rem] -translate-x-1/2 rounded-full bg-[radial-gradient(ellipse_at_center,#d4a84322,transparent_70%)] blur-2xl"
        />
        <p className="mj-rise marketing-eyebrow">Windows 10 / 11 · Free &amp; Open Source</p>
        <h1 className="mj-rise mj-rise-d1 mt-3 text-4xl font-black tracking-tight text-foreground sm:text-5xl">
          Download{" "}
          <span className="bg-gradient-to-r from-[#f0ca69] via-gold to-[#c49230] bg-clip-text text-transparent">
            MJOLNIR Launcher
          </span>
        </h1>
        <p className="mj-rise mj-rise-d2 mx-auto mt-4 max-w-xl text-base leading-7 text-text-muted sm:text-lg">
          Your way into Campaign Evolved multiplayer. Install all 19 classic Halo CE maps, Halo 2
          maps, community mods, and creator tools from one signed launcher.
        </p>
      </header>

      {/* Primary Download Card */}
      <div className="mj-rise mj-rise-d3 mj-hud-corners relative mb-8 overflow-hidden rounded-2xl border border-gold/35 bg-gradient-to-b from-surface-card/90 to-surface p-6 shadow-[0_24px_56px_-28px_rgba(212,168,67,0.3)] sm:p-8">
        <div className="mb-6 flex items-start gap-4">
          <div className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-gold/30 bg-gold/12 text-gold sm:size-14">
            <Download className="size-6 sm:size-7" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h2 className="text-xl font-bold text-foreground">Windows Installer (.exe)</h2>
              <span className="rounded-full border border-accent-green/35 bg-accent-green/10 px-2.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-accent-green">
                Auto-updating
              </span>
            </div>
            <p className="mt-1 text-sm text-text-muted">
              Windows 10/11 (64-bit) · Steam &amp; Game Pass compatible · Ed25519 verified updates
            </p>
          </div>
        </div>

        <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
          <Link
            href="https://releases.mjolnircore.com/launcher/latest/MJOLNIR-Launcher-latest-setup.exe"
            className="marketing-button-primary justify-center sm:px-6"
          >
            <Download className="size-5 shrink-0" />
            Download the installer
          </Link>
          {/* Not releases/latest: mods and tools publish releases from this
              repository too, so "latest" is rarely the launcher. */}
          <Link
            href="https://github.com/devnull9090/mjolnir-core/releases?q=launcher-v&expanded=true"
            target="_blank"
            className="marketing-button-secondary justify-center"
          >
            <GitHubIcon className="size-5 shrink-0" />
            All releases on GitHub
          </Link>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-border/80 pt-4 text-xs text-text-muted">
          <span className="inline-flex items-center gap-1.5">
            <CheckCircle aria-hidden="true" className="size-3.5 text-accent-green" />
            SHA-256 published per build
          </span>
          <span className="inline-flex items-center gap-1.5">
            <CheckCircle aria-hidden="true" className="size-3.5 text-accent-green" />
            Handles UE4SS, maps &amp; updates automatically
          </span>
          <span className="inline-flex items-center gap-1.5">
            <CheckCircle aria-hidden="true" className="size-3.5 text-accent-green" />
            Supports <code className="text-foreground">mjolnir://</code> one-click lobby joins
          </span>
        </div>
      </div>

      {/* Setup Steps */}
      <Reveal>
        <section className="mb-8 rounded-2xl border border-gold/25 bg-surface p-6 sm:p-8">
          <p className="marketing-eyebrow">Installed? Bring your friends.</p>
          <h2 className="mb-7 mt-2.5 text-2xl font-black tracking-tight">
            Set up Campaign Evolved multiplayer
          </h2>
          <PlaySteps />
          <p className="mt-6 text-sm leading-7 text-text-muted">
            Multiplayer is in alpha with up to 16 players. Works on Steam and Game Pass, and the two
            can play together. Each player needs their own copy of the game and the same maps; a
            missing map can be downloaded from inside the game.
          </p>
          <Link
            href="/multiplayer#faq"
            className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:underline"
          >
            Multiplayer setup &amp; FAQs <ArrowRight className="size-4" />
          </Link>
        </section>
      </Reveal>

      {/* Hash Verification */}
      <Reveal delay={40}>
        <section className="mb-8 rounded-2xl border border-border bg-surface-raised p-6 sm:p-8">
          <div className="mb-6 flex items-start gap-4">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-accent-green/25 bg-accent-green/10 text-accent-green sm:size-14">
              <Shield className="size-6 sm:size-7" />
            </div>
            <div className="min-w-0">
              <h2 className="text-xl font-bold text-foreground">Verify Your Download</h2>
              <p className="mt-1 text-sm text-text-muted">
                Always verify the SHA-256 checksum to confirm your installer is authentic and unmodified.
              </p>
            </div>
          </div>

          <div className="space-y-6">
            {/* Step 1 */}
            <div className="flex items-start gap-3.5">
              <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-gold/30 bg-gold/12 font-mono text-xs font-bold text-gold">
                1
              </span>
              <div className="min-w-0 flex-1">
                <p className="mb-3 text-sm font-semibold text-foreground">
                  Official Build Checksums (Latest Release)
                </p>
                <ChecksumViewer />
              </div>
            </div>

            {/* Step 2 */}
            <div className="flex items-start gap-3.5">
              <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-gold/30 bg-gold/12 font-mono text-xs font-bold text-gold">
                2
              </span>
              <div className="min-w-0 flex-1 space-y-3">
                <p className="text-sm font-semibold text-foreground">
                  Compute the hash of your downloaded file
                </p>
                <CopyCommand
                  label="PowerShell (Windows)"
                  command={`(Get-FileHash .\\MJOLNIR-Launcher*-setup.exe -Algorithm SHA256).Hash`}
                />
                <CopyCommand
                  label="Command Prompt"
                  command={`certutil -hashfile MJOLNIR-Launcher-latest-setup.exe SHA256`}
                />
              </div>
            </div>

            {/* Step 3 */}
            <div className="flex items-start gap-3.5">
              <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-gold/30 bg-gold/12 font-mono text-xs font-bold text-gold">
                3
              </span>
              <div className="min-w-0 flex-1">
                <p className="mb-2 text-sm font-semibold text-foreground">Compare the hashes</p>
                <div className="flex items-start gap-2.5 rounded-xl border border-accent-green/25 bg-accent-green/5 p-3.5">
                  <CheckCircle className="mt-0.5 size-4 shrink-0 text-accent-green" />
                  <p className="text-sm text-text-muted">
                    If the hash you computed <strong className="text-foreground">exactly matches</strong>{" "}
                    the one in <code className="rounded bg-surface-card px-1.5 py-0.5 text-xs text-foreground">checksums.txt</code>,
                    your download is authentic and unmodified.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </Reveal>

      {/* Companion Tools & CLI */}
      <div className="mb-8 space-y-6">
        <Reveal delay={60}>
          <SpotlightCard className="rounded-2xl border border-border bg-surface-raised p-6 sm:p-8">
            <div className="relative z-[2] flex items-start gap-4">
              <div className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-gold/25 bg-gold/10 text-gold sm:size-14">
                <Wrench className="size-6 sm:size-7" />
              </div>
              <div className="min-w-0">
                <h2 className="text-xl font-bold text-foreground">The tools install from here too</h2>
                <p className="mt-1.5 text-sm leading-6 text-text-muted">
                  The launcher&apos;s Tools view installs and updates the MJOLNIR Tag Editor — the
                  Guerilla-style editor for the game&apos;s tags, textures, audio and scripts — and
                  checks every build against its published hash.
                </p>
                <Link
                  href="/tools"
                  className="mt-3.5 inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline"
                >
                  See the tools
                  <ArrowRight className="size-4" />
                </Link>
              </div>
            </div>
          </SpotlightCard>
        </Reveal>

        <Reveal delay={80}>
          <div className="rounded-2xl border border-border bg-surface-raised p-6 sm:p-8">
            <div className="flex items-start gap-4">
              <div className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-gold/25 bg-gold/10 text-gold sm:size-14">
                <Terminal className="size-6 sm:size-7" />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="text-xl font-bold text-foreground">Prefer a command line?</h2>
                <p className="mt-1.5 text-sm leading-6 text-text-muted">
                  <code className="rounded bg-surface-card px-1.5 py-0.5 text-foreground">mjolnir</code>{" "}
                  reads and edits the same tag data from a terminal — list a group, print a tag&apos;s
                  decoded fields, change one, and bake the result into a container the game loads. It
                  runs on <strong className="text-foreground">Windows, Linux and macOS</strong>, with a
                  checksum published for every build.
                </p>
                <CliInstallTabs />
                <p className="mt-2.5 text-xs leading-5 text-text-dim">
                  Also as <code>.deb</code> and <code>.rpm</code>, or a plain archive. The Linux build
                  is statically linked, so it runs on any distribution.
                </p>
                <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
                  <Link
                    href="https://github.com/devnull9090/mjolnir-core/releases?q=cli-v"
                    target="_blank"
                    className="inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline"
                  >
                    Download an archive
                    <ExternalLink className="size-4" />
                  </Link>
                  <Link
                    href="/docs/guides/getting-started"
                    className="inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline"
                  >
                    Read the walkthrough
                    <ArrowRight className="size-4" />
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </div>

      {/* System Requirements */}
      <Reveal delay={100}>
        <section className="rounded-2xl border border-border bg-surface-raised p-6 sm:p-8">
          <p className="marketing-eyebrow">Compatibility</p>
          <h2 className="mb-5 mt-2 text-lg font-bold text-foreground">System Requirements</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {[
              { icon: Monitor, label: "OS", value: "Windows 10/11 (64-bit)" },
              { icon: Cpu, label: "Runtime", value: "WebView2 (included in Win 11)" },
              { icon: Gamepad2, label: "Game", value: "Halo Campaign Evolved (Steam or Game Pass)" },
              { icon: HardDrive, label: "Disk", value: "~50 MB for launcher" },
            ].map(({ icon: Icon, label, value }) => (
              <div
                key={label}
                className="flex items-center gap-3.5 rounded-xl border border-border bg-surface-card p-3.5"
              >
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-gold/20 bg-gold/10 text-gold">
                  <Icon aria-hidden="true" className="size-4" />
                </span>
                <div className="min-w-0">
                  <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-text-dim">
                    {label}
                  </p>
                  <p className="text-sm font-medium text-foreground">{value}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </Reveal>
    </PageShell>
  );
}
