import { useEffect } from "react";
import { useEditor } from "./stores/editor-store";
import { SetupPanel } from "./components/SetupPanel";
import { LoadingPanel } from "./components/LoadingPanel";
import { TagTree } from "./components/TagTree";
import { Inspector } from "./components/Inspector";
import { FormInspector } from "./components/FormInspector";
import { TextureViewer } from "./components/TextureViewer";
import { SoundViewer } from "./components/SoundViewer";
import { TabBar } from "./components/TabBar";

export default function App() {
  const status = useEditor((s) => s.status);
  const viewMode = useEditor((s) => s.viewMode);
  const { tabs, activeTab } = useEditor();
  const detect = useEditor((s) => s.detect);

  useEffect(() => {
    void detect();
  }, [detect]);

  // Detection and opening are automatic, so they get a spinner rather than the
  // setup form; the form is for when we need the user to point us somewhere.
  if (status === "detecting") {
    return <LoadingPanel label="Looking for your installation…" />;
  }
  if (status === "opening") {
    return <LoadingPanel label="Reading the tag catalogue…" />;
  }
  if (status !== "ready") {
    return <SetupPanel />;
  }

  const active = tabs.find((t) => t.id === activeTab);

  return (
    <div className="flex h-full min-h-0">
      <TagTree />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <TabBar />
        {active === undefined ? (
          <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-dim">
            Open a tag, texture or sound from the list.
          </div>
        ) : active.kind === "texture" ? (
          <TextureViewer />
        ) : active.kind === "sound" ? (
          <SoundViewer />
        ) : viewMode === "form" ? (
          <FormInspector />
        ) : (
          <Inspector />
        )}
      </div>
    </div>
  );
}
