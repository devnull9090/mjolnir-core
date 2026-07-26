"use client";

import { useState, useEffect } from "react";
import { Copy, Check, Hash, ExternalLink } from "lucide-react";

interface ChecksumInfo {
  version: string;
  msi_name: string;
  msi_hash: string | null;
  nsis_name: string;
  nsis_hash: string | null;
  checksums_url: string;
}

export default function ChecksumViewer() {
  const [data, setData] = useState<ChecksumInfo | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/releases/latest")
      .then((res) => res.json())
      .then((json) => setData(json))
      .catch((err) => console.error("Failed to load release checksums:", err))
      .finally(() => setLoading(false));
  }, []);

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  if (loading) {
    return (
      <div className="p-6 rounded-xl bg-surface-card border border-border flex items-center justify-center gap-3 text-sm text-text-muted">
        <div className="w-4 h-4 border-2 border-gold border-t-transparent rounded-full animate-spin" />
        Fetching latest build checksums from CDN...
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-4">
      {/* MSI Hash Box */}
      {data.msi_hash && (
        <div className="p-4 rounded-xl bg-surface-card border border-border">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <span className="text-xs font-semibold text-gold uppercase tracking-wider flex items-center gap-1.5 min-w-0">
              <Hash className="w-3.5 h-3.5 flex-shrink-0" />
              <span className="truncate">MSI Installer ({data.msi_name})</span>
            </span>
            <button
              onClick={() => copyToClipboard(data.msi_hash!, "msi")}
              className="px-3 py-2 rounded-md bg-surface-raised border border-border-bright text-xs text-text-muted hover:text-foreground hover:border-gold/40 transition-all flex items-center gap-1.5 cursor-pointer flex-shrink-0"
            >
              {copiedKey === "msi" ? (
                <>
                  <Check className="w-3.5 h-3.5 text-accent-green" />
                  <span className="text-accent-green font-semibold">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  Copy SHA-256
                </>
              )}
            </button>
          </div>
          <code className="block p-2.5 rounded bg-background border border-border/50 text-xs font-mono text-gold break-all">
            {data.msi_hash}
          </code>
        </div>
      )}

      {/* NSIS Executable Hash Box */}
      {data.nsis_hash && (
        <div className="p-4 rounded-xl bg-surface-card border border-border">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <span className="text-xs font-semibold text-accent-blue uppercase tracking-wider flex items-center gap-1.5 min-w-0">
              <Hash className="w-3.5 h-3.5 flex-shrink-0" />
              <span className="truncate">EXE Setup ({data.nsis_name})</span>
            </span>
            <button
              onClick={() => copyToClipboard(data.nsis_hash!, "nsis")}
              className="px-3 py-2 rounded-md bg-surface-raised border border-border-bright text-xs text-text-muted hover:text-foreground hover:border-accent-blue/40 transition-all flex items-center gap-1.5 cursor-pointer flex-shrink-0"
            >
              {copiedKey === "nsis" ? (
                <>
                  <Check className="w-3.5 h-3.5 text-accent-green" />
                  <span className="text-accent-green font-semibold">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  Copy SHA-256
                </>
              )}
            </button>
          </div>
          <code className="block p-2.5 rounded bg-background border border-border/50 text-xs font-mono text-accent-blue break-all">
            {data.nsis_hash}
          </code>
        </div>
      )}

      <div className="flex items-center justify-between text-xs text-text-dim px-1 pt-1">
        <span>Latest Release: <strong className="text-gold">v{data.version}</strong></span>
        <a
          href={data.checksums_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent-blue hover:underline flex items-center gap-1"
        >
          View raw checksums.txt
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </div>
  );
}
