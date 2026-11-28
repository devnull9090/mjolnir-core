import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { ActionButton, ErrorNote, RefreshIcon, Spinner } from "@mjolnir/hub-kit";

interface ToolStatus {
  id: string;
  name: string;
  description: string;
  installed_version: string | null;
  latest_version: string | null;
  update_available: boolean;
  size: number;
  /** Why the latest version is unknown, when it is. */
  error: string | null;
}

interface ToolProgress {
  id: string;
  stage: string;
  message: string;
  percent: number;
}

function humanSize(bytes: number): string {
  if (!bytes) return "";
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

export default function Tools() {
  const [tools, setTools] = useState<ToolStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [progress, setProgress] = useState<Record<string, ToolProgress>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setTools(await invoke<ToolStatus[]>("get_tools"));
      setLoadError(null);
    } catch (e) {
      console.error(e);
      setLoadError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const stop = listen<ToolProgress>("tool-progress", (event) => {
      setProgress((p) => ({ ...p, [event.payload.id]: event.payload }));
    });
    return () => {
      void stop.then((unlisten) => unlisten());
    };
  }, []);

  async function install(id: string) {
    setErrors((e) => ({ ...e, [id]: "" }));
    try {
      await invoke("install_tool", { id });
      await refresh();
    } catch (e) {
      setErrors((prev) => ({ ...prev, [id]: String(e) }));
    } finally {
      setProgress((p) => {
        const next = { ...p };
        delete next[id];
        return next;
      });
    }
  }

  async function launch(id: string) {
    setErrors((e) => ({ ...e, [id]: "" }));
    try {
      await invoke("launch_tool", { id });
    } catch (e) {
      setErrors((prev) => ({ ...prev, [id]: String(e) }));
    }
  }

  async function uninstall(id: string) {
    try {
      await invoke("uninstall_tool", { id });
      await refresh();
    } catch (e) {
      setErrors((prev) => ({ ...prev, [id]: String(e) }));
    }
  }

  if (loading && tools.length === 0) {
    return (
      <div className="max-w-5xl mx-auto flex items-center gap-2 text-sm text-text-secondary">
        <Spinner className="w-4 h-4" /> Checking for tools…
      </div>
    );
  }

  return (
    <div className="space-y-4 max-w-5xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Tools</h2>
          <p className="text-sm text-text-secondary mt-0.5">
            Companion apps, downloaded and kept up to date by the launcher.
          </p>
        </div>
        <ActionButton
          tone="neutral"
          size="sm"
          onClick={() => void refresh()}
          disabled={loading}
        >
          <RefreshIcon className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </ActionButton>
      </div>

      {loadError && (
        <ErrorNote>Could not load companion tools ({loadError}).</ErrorNote>
      )}

      {!loadError && tools.length === 0 && (
        <div className="rounded-xl border border-dashed border-border-subtle bg-surface-secondary/50 p-6 text-center text-sm text-text-secondary">
          No companion tools are available right now.
        </div>
      )}

      {tools.map((tool) => {
        const busy = progress[tool.id];
        const installed = tool.installed_version !== null;
        return (
          <div
            key={tool.id}
            className="launcher-card bg-surface-secondary border border-border-subtle rounded-xl p-5 hover:border-mjolnir-gold/40"
          >
            <div className="flex items-start gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-semibold">{tool.name}</h3>
                  {installed && (
                    <span className="text-[11px] px-1.5 py-0.5 rounded bg-surface-hover text-text-secondary">
                      v{tool.installed_version}
                    </span>
                  )}
                  {tool.update_available && (
                    <span className="text-[11px] px-1.5 py-0.5 rounded bg-mjolnir-gold/15 text-mjolnir-gold">
                      v{tool.latest_version} available
                    </span>
                  )}
                </div>
                <p className="text-sm text-text-secondary mt-1">{tool.description}</p>

                {!installed && tool.latest_version && (
                  <p className="text-xs text-text-secondary mt-1">
                    v{tool.latest_version}
                    {tool.size ? ` · ${humanSize(tool.size)}` : ""}
                  </p>
                )}
                {tool.error && (
                  <p className="text-xs text-amber-400/80 mt-1">
                    Could not check for updates: {tool.error}
                  </p>
                )}
                {errors[tool.id] && (
                  <p className="text-xs text-red-400 mt-1">{errors[tool.id]}</p>
                )}
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {installed && (
                  <button
                    onClick={() => void launch(tool.id)}
                    disabled={!!busy}
                    className="px-3 py-2 rounded-lg text-sm font-semibold
                      bg-gradient-to-r from-mjolnir-gold to-mjolnir-gold-dim text-surface-primary
                      hover:brightness-110 disabled:opacity-50 cursor-pointer transition-all"
                  >
                    Open
                  </button>
                )}
                {(!installed || tool.update_available) && (
                  <button
                    onClick={() => void install(tool.id)}
                    disabled={!!busy || !tool.latest_version}
                    className="px-3 py-2 rounded-lg text-sm font-medium
                      border border-mjolnir-gold/40 text-mjolnir-gold
                      hover:bg-mjolnir-gold/10 disabled:opacity-40 cursor-pointer transition-all"
                  >
                    {busy ? "Working…" : installed ? "Update" : "Install"}
                  </button>
                )}
                {installed && !busy && (
                  <button
                    onClick={() => void uninstall(tool.id)}
                    className="px-2 py-2 rounded-lg text-xs text-text-secondary
                      hover:text-red-400 hover:bg-surface-hover cursor-pointer transition-all"
                    title="Remove this tool"
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>

            {busy && (
              <div className="mt-3">
                <div className="h-1.5 rounded-full bg-surface-hover overflow-hidden">
                  <div
                    className="h-full bg-mjolnir-gold transition-all duration-200"
                    style={{ width: `${busy.percent}%` }}
                  />
                </div>
                <p className="text-xs text-text-secondary mt-1">{busy.message}</p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
