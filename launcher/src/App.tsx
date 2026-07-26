import { useState } from "react";
import Sidebar from "./components/Sidebar";
import ModList from "./components/ModList";
import Header from "./components/Header";

export type View = "mods" | "browse" | "settings";

function App() {
  const [activeView, setActiveView] = useState<View>("mods");

  return (
    <div className="flex h-screen w-screen bg-surface-primary">
      <Sidebar activeView={activeView} onNavigate={setActiveView} />
      <div className="flex flex-col flex-1 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          {activeView === "mods" && <ModList />}
          {activeView === "browse" && <BrowsePlaceholder />}
          {activeView === "settings" && <SettingsPlaceholder />}
        </main>
      </div>
    </div>
  );
}

function BrowsePlaceholder() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-text-secondary">
      <svg className="w-16 h-16 mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
      <p className="text-lg font-medium">Browse Community Mods</p>
      <p className="text-sm mt-1">Coming Soon — MJOLNIR Hub</p>
    </div>
  );
}

function SettingsPlaceholder() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-text-secondary">
      <svg className="w-16 h-16 mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.573-1.066z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
      <p className="text-lg font-medium">Settings</p>
      <p className="text-sm mt-1">Configure game path, UE4SS version, preferences</p>
    </div>
  );
}

export default App;
