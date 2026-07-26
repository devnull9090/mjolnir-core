import { useEffect, useState } from "react";
import { check, Update } from "@tauri-apps/plugin-updater";

export default function UpdaterBanner() {
  const [update, setUpdate] = useState<Update | null>(null);
  const [status, setStatus] = useState<"idle" | "available" | "downloading" | "done" | "error">("idle");
  const [downloadedBytes, setDownloadedBytes] = useState(0);
  const [totalBytes, setTotalBytes] = useState(0);

  useEffect(() => {
    async function checkForUpdates() {
      try {
        const updateResult = await check();
        if (updateResult) {
          setUpdate(updateResult);
          setStatus("available");
        }
      } catch (err) {
        console.log("No update available or check failed:", err);
      }
    }

    checkForUpdates();
  }, []);

  const handleInstallUpdate = async () => {
    if (!update) return;

    try {
      setStatus("downloading");
      let downloaded = 0;
      let total = 0;

      await update.downloadAndInstall((event) => {
        switch (event.event) {
          case "Started":
            total = event.data.contentLength || 0;
            setTotalBytes(total);
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

  if (status === "idle" || !update) return null;

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

      <div>
        {status === "available" && (
          <button
            onClick={handleInstallUpdate}
            className="px-3 py-1 rounded bg-mjolnir-gold text-surface-primary text-xs font-bold hover:brightness-110 transition-all cursor-pointer"
          >
            Update Now
          </button>
        )}
        {status === "downloading" && (
          <span className="text-xs text-mjolnir-gold font-semibold">Downloading...</span>
        )}
        {status === "done" && (
          <span className="text-xs text-accent-green font-semibold">Restarting launcher...</span>
        )}
        {status === "error" && (
          <span className="text-xs text-red-400 font-semibold">Update failed</span>
        )}
      </div>
    </div>
  );
}
