import { useState } from "react";
import Sidebar from "./components/Sidebar";
import ModList from "./components/ModList";
import Header from "./components/Header";
import UpdaterBanner, { useUpdater } from "./components/UpdaterBanner";
import Settings from "./components/Settings";
import Tools from "./components/Tools";

export type View = "mods" | "tools" | "browse" | "settings";

function App() {
  const [activeView, setActiveView] = useState<View>("mods");
  const updater = useUpdater();

  return (
    <div className="flex h-screen w-screen bg-surface-primary">
      <Sidebar activeView={activeView} onNavigate={setActiveView} updater={updater} />
      <div className="flex flex-col flex-1 overflow-hidden">
        <UpdaterBanner updater={updater} />
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          {activeView === "mods" && <ModList />}
          {activeView === "tools" && <Tools />}
          {activeView === "browse" && <BrowsePlaceholder />}
          {activeView === "settings" && <Settings />}
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

export default App;
