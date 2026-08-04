import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const resolvePath = (relative: string) =>
  fileURLToPath(new URL(relative, import.meta.url));

// The launcher owns port 1420, so the editor sits on 1430 to allow running
// both at once.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false,

  resolve: {
    alias: {
      // The shared changelog types and the "What's new" dialog, shared with
      // the website and the launcher. Source, not a package — see
      // hub/src/kit/README.md.
      "@mjolnir/hub-kit": resolvePath("../../hub/src/kit/index.ts"),
      // That source sits outside this project, so `react` is not reachable by
      // walking up from it. Pinning both here is also what keeps a single
      // React instance in the bundle, which hooks require.
      react: resolvePath("./node_modules/react"),
      "react-dom": resolvePath("./node_modules/react-dom"),
    },
  },

  server: {
    port: 1430,
    strictPort: true,
    watch: {
      // Rust sources are rebuilt by the Tauri CLI, not Vite.
      ignored: ["**/src-tauri/**"],
    },
    hmr: { port: 1431 },
    fs: {
      // The dev server must be allowed to serve the shared kit, which sits
      // outside this project's root.
      allow: [resolvePath("."), resolvePath("../../hub/src/kit")],
    },
  },
  build: {
    // Must match src-tauri/tauri.conf.json `frontendDist` ("../dist" relative
    // to src-tauri, i.e. this app's own dist), or `tauri build` cannot find
    // the web assets.
    outDir: "dist",
    emptyOutDir: true,
  },
});
