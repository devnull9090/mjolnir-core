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
    outDir: "../dist",
    emptyOutDir: true,
  },
});
