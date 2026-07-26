import { useEffect, useState } from "react";
import { check, Update } from "@tauri-apps/plugin-updater";

export type UpdateStatus = "idle" | "checking" | "available" | "dismissed" | "downloading" | "done" | "error";

export interface UpdateState {
  update: Update | null;
  status: UpdateStatus;
  version: string | null;
  downloadedBytes: number;
  totalBytes: number;
  handleInstall: () => Promise<void>;
  dismiss: () => void;
  recheck: () => Promise<void>;
}

export function useUpdater(): UpdateState {
  const [update, setUpdate] = useState<Update | null>(null);
  const [status, setStatus] = useState<UpdateStatus>("idle");
  const [version, setVersion] = useState<string | null>(null);
  const [downloadedBytes, setDownloadedBytes] = useState(0);
  const [totalBytes, setTotalBytes] = useState(0);

  const checkForUpdates = async () => {
    try {
      setStatus("checking");
      const updateResult = await check();
      if (updateResult) {
        setUpdate(updateResult);
        setVersion(updateResult.version);
        setStatus("available");
      } else {
        setStatus("idle");
      }
    } catch (err) {
      console.log("Update check failed:", err);
      setStatus("idle");
    }
  };

  useEffect(() => {
    checkForUpdates();
  }, []);

  const handleInstall = async () => {
    if (!update) return;

    try {
      setStatus("downloading");
      let downloaded = 0;

      await update.downloadAndInstall((event) => {
        switch (event.event) {
          case "Started":
            setTotalBytes(event.data.contentLength || 0);
            break;
          case "Progress":
            downloaded += event.data.chunkLength;
            setDownloadedBytes(downloaded);
            break;
          case "Finished":
            setStatus("done");
            break;
        }
      });
    } catch (err) {
      console.error("Failed to install update:", err);
      setStatus("error");
    }
  };

  const dismiss = () => {
    setStatus("dismissed");
  };

  return {
    update,
    status,
    version,
    downloadedBytes,
    totalBytes,
    handleInstall,
    dismiss,
    recheck: checkForUpdates,
  };
}

interface UpdaterBannerProps {
  updater: UpdateState;
}

export default function UpdaterBanner({ updater }: UpdaterBannerProps) {
  const { update, status, downloadedBytes, totalBytes, handleInstall, dismiss } = updater;

  // Don't show if idle, checking, dismissed, or no update
  if (status === "idle" || status === "checking" || status === "dismissed" || !update) return null;

  return (
    <div className="bg-mjolnir-gold/15 border-b border-mjolnir-gold/30 px-6 py-2.5 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-mjolnir-gold animate-pulse" />
        <span className="text-xs text-text-primary font-medium">
          Update Available: <strong className="text-mjolnir-gold">v{update.version}</strong>
        </span>
        {status === "downloading" && totalBytes > 0 && (
          <span className="text-xs text-text-secondary">
            ({Math.round((downloadedBytes / totalBytes) * 100)}%)
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {status === "available" && (
          <>
            <button
              onClick={handleInstall}
              className="px-3 py-1 rounded bg-mjolnir-gold text-surface-primary text-xs font-bold hover:brightness-110 transition-all cursor-pointer"
            >
              Update Now
            </button>
            <button
              onClick={dismiss}
              className="px-2 py-1 rounded text-xs text-text-secondary hover:text-text-primary hover:bg-surface-hover transition-all cursor-pointer"
              title="Dismiss"
            >
              ✕
            </button>
          </>
        )}
        {status === "downloading" && (
          <span className="text-xs text-mjolnir-gold font-semibold">Downloading...</span>
        )}
        {status === "done" && (
          <span className="text-xs text-accent-green font-semibold">Restarting launcher...</span>
        )}
        {status === "error" && (
          <button
            onClick={handleInstall}
            className="text-xs text-red-400 font-semibold hover:text-red-300 cursor-pointer"
          >
            Retry Update
          </button>
        )}
      </div>
    </div>
  );
}
