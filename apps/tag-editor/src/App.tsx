import { useEffect } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { WhatsNew } from "@mjolnir/hub-kit";
import { useWhatsNew } from "./lib/whats-new";
import { useEditor } from "./stores/editor-store";
import { SetupPanel } from "./components/SetupPanel";
import { LoadingPanel } from "./components/LoadingPanel";
import { TagTree } from "./components/TagTree";
import { Inspector } from "./components/Inspector";
import { FormInspector } from "./components/FormInspector";
import { TextureViewer } from "./components/TextureViewer";
import { SoundViewer } from "./components/SoundViewer";
import { ScriptViewer } from "./components/ScriptViewer";
import { ScenarioViewer } from "./components/ScenarioViewer";
import { ModelViewer } from "./components/ModelViewer";
import { MeshViewer } from "./components/MeshViewer";
import { TabBar } from "./components/TabBar";
import { Shortcuts } from "./components/Shortcuts";
import { QuickOpen } from "./components/QuickOpen";
import { ContextMenuHost } from "./components/ContextMenu";
import { NewTagDialog } from "./components/NewTagDialog";
import { TsvPasteDialog } from "./components/TsvPasteDialog";
import { MODEL_GROUPS } from "./stores/editor-store";

export default function App() {
  const whatsNew = useWhatsNew();

  return (
    <>
      <Editor />
      {/* Outside the editor, and above it: it applies whatever the editor is
          doing, including the setup form a first-time user is looking at. */}
      <WhatsNew
        releases={whatsNew.releases}
        onClose={whatsNew.dismiss}
        onOpenLink={(url) => void openUrl(url)}
      />
    </>
  );
}

function Editor() {
  const status = useEditor((s) => s.status);
  const viewMode = useEditor((s) => s.viewMode);
  const { tabs, activeTab } = useEditor();
  const tag = useEditor((s) => s.tag);
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
  // Only a scenario carries script, so the script view falls back to the form
  // for anything else rather than showing an empty panel. Same rule for the
  // model view and the groups that carry geometry.
  const scriptable = tag?.group === "scenario";
  const modelable = MODEL_GROUPS.includes(tag?.group ?? "");

  return (
    <div className="flex h-full min-h-0">
      <Shortcuts />
      <QuickOpen />
      <NewTagDialog />
      <TsvPasteDialog />
      <ContextMenuHost />
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
        ) : active.kind === "mesh" ? (
          <MeshViewer />
        ) : viewMode === "script" && scriptable ? (
          <ScriptViewer />
        ) : viewMode === "world" && scriptable ? (
          <ScenarioViewer />
        ) : viewMode === "model" && modelable ? (
          <ModelViewer />
        ) : viewMode === "tree" ? (
          // Keyed per tab so per-tab UI state can never leak between two tags
          // of the same group, whose child keys would otherwise line up.
          <Inspector key={active.id} />
        ) : (
          <FormInspector key={active.id} />
        )}
      </div>
    </div>
  );
}
