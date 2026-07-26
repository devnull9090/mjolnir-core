import { useState } from "react";

interface Mod {
  name: string;
  description: string;
  enabled: boolean;
  version: string;
}

const DEFAULT_MODS: Mod[] = [
  { name: "MJOLNIRCore", description: "Core runtime & UEHelpers library", enabled: true, version: "1.0.0" },
  { name: "MJOLNIRFlyCam", description: "Free debug camera with WASD, mouse look, HUD toggle", enabled: true, version: "1.0.0" },
  { name: "MJOLNIRConsoleEnabler", description: "UE5 developer console enabler (~ / Tab / F10)", enabled: true, version: "1.0.0" },
  { name: "MJOLNIRMultiplayer", description: "Session hosting, travel, admin commands", enabled: true, version: "0.1.0" },
  { name: "MJOLNIRDiscovery", description: "UFunction dumper & travel logging diagnostics", enabled: false, version: "0.1.0" },
];

export default function ModList() {
  const [mods, setMods] = useState<Mod[]>(DEFAULT_MODS);

  const toggleMod = (index: number) => {
    setMods((prev) =>
      prev.map((m, i) => (i === index ? { ...m, enabled: !m.enabled } : m))
    );
  };

  const enabledCount = mods.filter((m) => m.enabled).length;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-text-primary">Installed Mods</h2>
          <p className="text-sm text-text-secondary mt-1">
            {enabledCount} of {mods.length} mods enabled
          </p>
        </div>
        <button className="px-4 py-2 text-sm font-medium rounded-lg bg-surface-card border border-border-subtle text-text-secondary hover:text-text-primary hover:border-mjolnir-gold/40 transition-all duration-150 cursor-pointer">
          + Install from file
        </button>
      </div>

      <div className="space-y-2">
        {mods.map((mod, index) => (
          <div
            key={mod.name}
            className={`group flex items-center gap-4 p-4 rounded-xl border transition-all duration-200
              ${
                mod.enabled
                  ? "bg-surface-card border-border-subtle hover:border-mjolnir-gold/30"
                  : "bg-surface-primary border-border-subtle/50 opacity-60 hover:opacity-80"
              }`}
          >
            {/* Toggle */}
            <button
              onClick={() => toggleMod(index)}
              className={`relative w-11 h-6 rounded-full transition-colors duration-200 cursor-pointer flex-shrink-0
                ${mod.enabled ? "bg-accent-green" : "bg-surface-hover"}`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-md transition-transform duration-200
                  ${mod.enabled ? "translate-x-5" : "translate-x-0"}`}
              />
            </button>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-sm text-text-primary">{mod.name}</span>
                <span className="text-[10px] text-text-secondary px-1.5 py-0.5 rounded bg-surface-hover">
                  v{mod.version}
                </span>
              </div>
              <p className="text-xs text-text-secondary mt-0.5 truncate">{mod.description}</p>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
              <button className="p-1.5 rounded-md text-text-secondary hover:text-accent-blue hover:bg-surface-hover transition-colors cursor-pointer" title="Settings">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 12.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 18.75a.75.75 0 110-1.5.75.75 0 010 1.5z" />
                </svg>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
