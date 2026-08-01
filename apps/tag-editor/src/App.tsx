import { useEffect } from "react";
import { useEditor } from "./stores/editor-store";
import { SetupPanel } from "./components/SetupPanel";
import { TagTree } from "./components/TagTree";
import { Inspector } from "./components/Inspector";
import { FormInspector } from "./components/FormInspector";
import { TextureViewer } from "./components/TextureViewer";
import { TabBar } from "./components/TabBar";

export default function App() {
  const status = useEditor((s) => s.status);
  const viewMode = useEditor((s) => s.viewMode);
  const { tabs, activeTab } = useEditor();
  const detect = useEditor((s) => s.detect);

  useEffect(() => {
    void detect();
  }, [detect]);

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
            Open a tag or texture from the list.
          </div>
        ) : active.kind === "texture" ? (
          <TextureViewer />
        ) : viewMode === "form" ? (
          <FormInspector />
        ) : (
          <Inspector />
        )}
      </div>
    </div>
  );
}
