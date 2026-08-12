import { useCallback, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { WhatsNew } from "@mjolnir/hub-kit";
import Sidebar from "./components/Sidebar";
import Library from "./components/Library";
import Header from "./components/Header";
import UpdaterBanner, { useUpdater } from "./components/UpdaterBanner";
import Settings from "./components/Settings";
import Tools from "./components/Tools";
import Browse from "./components/Browse";
import Updates from "./components/Updates";
import { ModDetail } from "./components/hub/ModDetail";
import { UserProfile } from "./components/hub/UserProfile";
import { HubShell } from "./hub/HubShell";
import { useHubLibrary } from "./hub/library";
import { useUpdates } from "./updates/useUpdates";
import { useWhatsNew } from "./updates/useWhatsNew";

/**
 * Three views answer three different questions, and nothing answers two:
 * My Mods is what is installed, Browse Hub is what exists, Updates is what
 * is out of date. Tools and Settings sit outside that loop.
 */
export type View = "mods" | "tools" | "browse" | "updates" | "settings";

function App() {
  const updater = useUpdater();
  // Lifted out of AppBody because the provider needs it too: author names
  // anywhere in the kit — a comment, a review, a mod byline — open a profile
  // through the context, and the provider sits above the body.
  const [openProfile, setOpenProfile] = useState<string | null>(null);

  return (
    // One hub session for the whole app: the account, the pairing dialog and
    // the API client are shared by My Mods and Browse Hub alike.
    <HubShell onOpenProfile={setOpenProfile}>
      <AppBody updater={updater} openProfile={openProfile} setOpenProfile={setOpenProfile} />
    </HubShell>
  );
}

function AppBody({
  updater,
  openProfile,
  setOpenProfile,
}: {
  updater: ReturnType<typeof useUpdater>;
  openProfile: string | null;
  setOpenProfile: (id: string | null) => void;
}) {
  const [activeView, setActiveView] = useState<View>("mods");
  const [openMod, setOpenMod] = useState<string | null>(null);
  // Both the library and the update manager read this; keeping one instance
  // means one set of hub calls and no disagreement about what is installed.
  const library = useHubLibrary();
  const whatsNew = useWhatsNew();
  // Keyed on the callback rather than on the hook's return value, which is a
  // fresh object every render: `useUpdates` keys its apply callback on this.
  const { announce: announceWhatsNew } = whatsNew;
  const announce = useCallback(
    (completed: Parameters<typeof announceWhatsNew>[0]) => void announceWhatsNew(completed),
    [announceWhatsNew],
  );
  const updates = useUpdates(updater, announce);

  // A profile opens over whatever is already there, so Back from it reveals
  // the mod you clicked the author on rather than dumping you at a list.
  // Opening a mod from a profile replaces it, which is the direction people
  // are actually travelling.
  const showMod = (slug: string) => {
    setOpenProfile(null);
    setOpenMod(slug);
  };
  const goTo = (view: View) => {
    setOpenProfile(null);
    setOpenMod(null);
    setActiveView(view);
  };

  return (
    <div className="flex h-screen w-screen bg-surface-primary">
      <Sidebar
        activeView={activeView}
        onNavigate={goTo}
        updater={updater}
        updateCount={updates.items.length}
      />
      <div className="flex flex-col flex-1 overflow-hidden">
        <UpdaterBanner updater={updater} onOpenUpdates={() => goTo("updates")} />
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          {openProfile ? (
            <UserProfile
              userId={openProfile}
              onBack={() => setOpenProfile(null)}
              onOpenMod={showMod}
            />
          ) : openMod ? (
            <ModDetail slug={openMod} library={library} onBack={() => setOpenMod(null)} />
          ) : (
            <>
              {activeView === "mods" && (
                <Library
                  library={library}
                  updateCount={updates.items.length}
                  onOpenMod={showMod}
                  onGoToUpdates={() => goTo("updates")}
                  onGoToBrowse={() => goTo("browse")}
                />
              )}
              {activeView === "tools" && <Tools />}
              {activeView === "browse" && <Browse library={library} onOpenMod={showMod} />}
              {activeView === "updates" && <Updates updates={updates} />}
              {activeView === "settings" && <Settings />}
            </>
          )}
        </main>
      </div>

      {/* Above everything, because it is the account of a change that has
          already happened to the app the player is looking at. */}
      <WhatsNew
        releases={whatsNew.releases}
        onClose={whatsNew.dismiss}
        onOpenLink={(url) => void openUrl(url)}
      />
    </div>
  );
}

export default App;
