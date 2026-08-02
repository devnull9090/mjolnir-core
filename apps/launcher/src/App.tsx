import { useState } from "react";
import Sidebar from "./components/Sidebar";
import ModList from "./components/ModList";
import Header from "./components/Header";
import UpdaterBanner, { useUpdater } from "./components/UpdaterBanner";
import Settings from "./components/Settings";
import Tools from "./components/Tools";
import Browse from "./components/Browse";

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
          {activeView === "browse" && <Browse />}
          {activeView === "settings" && <Settings />}
        </main>
      </div>
    </div>
  );
}

export default App;
