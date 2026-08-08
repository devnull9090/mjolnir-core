import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Download,
  Shield,
  Terminal,
  CheckCircle,
  ExternalLink,
  Wrench,
} from "lucide-react";
import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { GitHubIcon } from "../components/icons";
import ChecksumViewer from "./ChecksumViewer";

export const metadata: Metadata = {
  title: "Download | MJOLNIR Core",
  description:
    "Download the MJOLNIR Launcher for Halo Campaign Evolved — one-click installs for signed mods and tools, with SHA-256 checksums to verify every build.",
  alternates: { canonical: "https://mjolnircore.com/download" },
  openGraph: {
    title: "Download the MJOLNIR Launcher",
    description:
      "One-click mod management for Halo Campaign Evolved. Auto-detects your game, verifies every download.",
    url: "https://mjolnircore.com/download",
    siteName: "MJOLNIR Core",
    type: "website",
  },
};

export default function DownloadPage() {
  return (
    <>
      <Navbar />

      <main className="pt-32 md:pt-36 pb-24 px-4 sm:px-6 max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-3xl sm:text-4xl font-black text-foreground mb-4">Download MJOLNIR Launcher</h1>
          <p className="text-text-muted text-lg max-w-xl mx-auto">
            One-click mod management for Halo Campaign Evolved. Auto-detects your game, installs mods, and launches via Steam.
          </p>
        </div>

        {/* Download Card */}
        <div className="rounded-2xl bg-surface-raised border border-border p-5 sm:p-8 mb-8">
          <div className="flex items-start gap-3 sm:gap-4 mb-6">
            <div className="w-11 h-11 sm:w-14 sm:h-14 rounded-xl bg-gold/10 text-gold flex items-center justify-center flex-shrink-0">
              <Download className="w-6 h-6 sm:w-7 sm:h-7" />
            </div>
            <div className="min-w-0">
              <h2 className="text-xl font-bold text-foreground">Windows Installer (.msi)</h2>
              <p className="text-sm text-text-muted mt-1">Requires Windows 10/11 (64-bit) and WebView2 runtime</p>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <Link
              href="https://github.com/devnull9090/mjolnir-core/releases/latest"
              target="_blank"
              className="w-full sm:w-auto px-5 py-3 rounded-xl font-bold text-sm bg-gradient-to-r from-gold to-gold-dim text-background hover:brightness-110 transition-all shadow-lg shadow-gold/20 flex items-center justify-center gap-2"
            >
              <GitHubIcon className="w-5 h-5 flex-shrink-0" />
              Download from GitHub Releases
            </Link>
            <span className="text-sm text-text-dim">or</span>
            <Link
              href="https://releases.mjolnircore.com/launcher/latest/MJOLNIR-Launcher-latest.msi"
              target="_blank"
              className="w-full sm:w-auto px-5 py-3 rounded-xl font-bold text-sm border border-border-bright text-text-muted hover:text-foreground hover:border-gold/40 transition-all flex items-center justify-center gap-2"
            >
              <ExternalLink className="w-4 h-4 flex-shrink-0" />
              Download from CDN
            </Link>
          </div>
        </div>

        {/* Hash Verification */}
        <div className="rounded-2xl bg-surface-raised border border-border p-5 sm:p-8 mb-8">
          <div className="flex items-start gap-3 sm:gap-4 mb-6">
            <div className="w-11 h-11 sm:w-14 sm:h-14 rounded-xl bg-accent-green/10 text-accent-green flex items-center justify-center flex-shrink-0">
              <Shield className="w-6 h-6 sm:w-7 sm:h-7" />
            </div>
            <div className="min-w-0">
              <h2 className="text-xl font-bold text-foreground">Verify Your Download</h2>
              <p className="text-sm text-text-muted mt-1">
                Always verify the SHA-256 checksum to ensure your download hasn&apos;t been tampered with.
              </p>
            </div>
          </div>

          <div className="space-y-6">
            {/* Step 1 */}
            <div className="flex items-start gap-3">
              <span className="w-7 h-7 rounded-full bg-gold/15 text-gold text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">1</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground mb-3">Official Build Checksums (Latest Release)</p>
                <ChecksumViewer />
              </div>
            </div>

            {/* Step 2 */}
            <div className="flex items-start gap-3">
              <span className="w-7 h-7 rounded-full bg-gold/15 text-gold text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">2</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground mb-2">Compute the hash of your downloaded file</p>
                <div className="space-y-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <Terminal className="w-3 h-3 text-text-dim" />
                      <span className="text-xs text-text-dim font-medium uppercase tracking-wider">PowerShell (Windows)</span>
                    </div>
                    <pre className="p-3 rounded-lg bg-surface-card border border-border text-sm font-mono text-foreground overflow-x-auto"><code>{`(Get-FileHash .\\MJOLNIR-Launcher*.msi -Algorithm SHA256).Hash`}</code></pre>
                  </div>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <Terminal className="w-3 h-3 text-text-dim" />
                      <span className="text-xs text-text-dim font-medium uppercase tracking-wider">Command Prompt</span>
                    </div>
                    <pre className="p-3 rounded-lg bg-surface-card border border-border text-sm font-mono text-foreground overflow-x-auto"><code>{`certutil -hashfile MJOLNIR-Launcher.msi SHA256`}</code></pre>
                  </div>
                </div>
              </div>
            </div>

            {/* Step 3 */}
            <div className="flex items-start gap-3">
              <span className="w-7 h-7 rounded-full bg-gold/15 text-gold text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">3</span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground mb-2">Compare the hashes</p>
                <div className="flex items-start gap-2 p-3 rounded-lg bg-accent-green/5 border border-accent-green/20">
                  <CheckCircle className="w-4 h-4 text-accent-green flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-text-muted">
                    If the hash you computed <strong className="text-foreground">exactly matches</strong> the one in <code className="px-1 py-0.5 rounded bg-surface-card text-xs">checksums.txt</code>,
                    your download is authentic and unmodified.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* The launcher is also how the tools install */}
        <div className="rounded-2xl bg-surface-raised border border-border p-5 sm:p-8 mb-8">
          <div className="flex items-start gap-3 sm:gap-4">
            <div className="w-11 h-11 sm:w-14 sm:h-14 rounded-xl bg-gold/10 text-gold flex items-center justify-center flex-shrink-0">
              <Wrench className="w-6 h-6 sm:w-7 sm:h-7" />
            </div>
            <div className="min-w-0">
              <h2 className="text-xl font-bold text-foreground">The tools install from here too</h2>
              <p className="text-sm text-text-muted mt-1 leading-6">
                The launcher&apos;s Tools view installs and updates the MJOLNIR Tag Editor — the
                Guerilla-style editor for the game&apos;s tags, textures, audio and scripts — and
                checks every build against its published hash.
              </p>
              <Link
                href="/tools"
                className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline"
              >
                See the tools
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>
        </div>

        {/* System Requirements */}
        <div className="rounded-2xl bg-surface-raised border border-border p-5 sm:p-8">
          <h2 className="text-lg font-bold text-foreground mb-4">System Requirements</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              { label: "OS", value: "Windows 10/11 (64-bit)" },
              { label: "Runtime", value: "WebView2 (included in Win 11)" },
              { label: "Game", value: "Halo Campaign Evolved (Steam)" },
              { label: "Disk", value: "~50 MB for launcher" },
            ].map((req) => (
              <div key={req.label} className="flex items-center gap-3 p-3 rounded-lg bg-surface-card border border-border">
                <span className="text-xs text-text-dim font-medium uppercase tracking-wider w-16">{req.label}</span>
                <span className="text-sm text-foreground">{req.value}</span>
              </div>
            ))}
          </div>
        </div>
      </main>

      <Footer />
    </>
  );
}
