import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The launcher owns port 1420, so the editor sits on 1430 to allow running
// both at once.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false,
  server: {
    port: 1430,
    strictPort: true,
    watch: {
      // Rust sources are rebuilt by the Tauri CLI, not Vite.
      ignored: ["**/src-tauri/**"],
    },
    hmr: { port: 1431 },
  },
  build: {
    // Must match src-tauri/tauri.conf.json `frontendDist` ("../dist" relative
    // to src-tauri, i.e. this app's own dist), or `tauri build` cannot find
    // the web assets.
    outDir: "dist",
    emptyOutDir: true,
  },
});
