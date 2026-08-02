import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// @ts-expect-error process is a nodejs global
const host = process.env.TAURI_DEV_HOST;

const resolvePath = (relative: string) =>
  fileURLToPath(new URL(relative, import.meta.url));

// https://vite.dev/config/
export default defineConfig(async () => ({
  plugins: [react(), tailwindcss()],

  resolve: {
    alias: {
      // The hub API client and community UI, shared with the website. Source,
      // not a package — see hub/src/kit/README.md.
      "@mjolnir/hub-kit": resolvePath("../../hub/src/kit/index.ts"),
      // That source lives outside this project, so `react` is not reachable
      // by walking up from it. Pinning both here is also what keeps a single
      // React instance in the bundle, which hooks require.
      react: resolvePath("./node_modules/react"),
      "react-dom": resolvePath("./node_modules/react-dom"),
    },
  },

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
    fs: {
      // The dev server must be allowed to serve the shared kit, which sits
      // outside this project's root.
      allow: [resolvePath("."), resolvePath("../../hub/src/kit")],
    },
  },
}));
