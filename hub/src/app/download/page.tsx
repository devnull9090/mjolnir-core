import Link from "next/link";
import {
  Download,
  Shield,
  Terminal,
  CheckCircle,
  ExternalLink,
} from "lucide-react";
import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import ChecksumViewer from "./ChecksumViewer";

function GitHubIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}

export default function DownloadPage() {
  return (
    <>
      <Navbar />

      <main className="pt-32 md:pt-36 pb-24 px-6 max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-3xl sm:text-4xl font-black text-foreground mb-4">Download MJOLNIR Launcher</h1>
          <p className="text-text-muted text-lg max-w-xl mx-auto">
            One-click mod management for Halo Campaign Evolved. Auto-detects your game, installs mods, and launches via Steam.
          </p>
        </div>

        {/* Download Card */}
        <div className="rounded-2xl bg-surface-raised border border-border p-6 sm:p-8 mb-8">
          <div className="flex items-start gap-4 mb-6">
            <div className="w-14 h-14 rounded-xl bg-gold/10 text-gold flex items-center justify-center flex-shrink-0">
              <Download className="w-7 h-7" />
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
        <div className="rounded-2xl bg-surface-raised border border-border p-6 sm:p-8 mb-8">
          <div className="flex items-start gap-4 mb-6">
            <div className="w-14 h-14 rounded-xl bg-accent-green/10 text-accent-green flex items-center justify-center flex-shrink-0">
              <Shield className="w-7 h-7" />
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

        {/* System Requirements */}
        <div className="rounded-2xl bg-surface-raised border border-border p-6 sm:p-8">
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
