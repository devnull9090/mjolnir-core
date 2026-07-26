import { useEffect } from "react";
import { useEditor } from "./stores/editor-store";
import { SetupPanel } from "./components/SetupPanel";
import { TagTree } from "./components/TagTree";
import { Inspector } from "./components/Inspector";

export default function App() {
  const status = useEditor((s) => s.status);
  const detect = useEditor((s) => s.detect);

  useEffect(() => {
    void detect();
  }, [detect]);

  if (status !== "ready") {
    return <SetupPanel />;
  }

  return (
    <div className="flex h-full min-h-0">
      <TagTree />
      <Inspector />
    </div>
  );
}
