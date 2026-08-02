/**
 * The launcher's hub client: the shared HubClient with a Tauri transport.
 *
 * Requests go through the `hub_api` command rather than the webview's own
 * fetch. Two reasons, both about the credential: the paired API key lives in
 * the Rust side and is attached there, so a compromised page cannot read it;
 * and requests are not subject to the webview's origin rules, so the same
 * code works in dev and in a packaged build.
 */
import { invoke } from "@tauri-apps/api/core";
import { createHubClient, type HubTransport } from "@mjolnir/hub-kit";

/** Where the hub lives, for links opened in a real browser. */
export const HUB_SITE = "https://mjolnircore.com";

const transport: HubTransport = async (req) => {
  const query = Object.entries(req.query ?? {})
    .filter(([, v]) => v !== undefined && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");

  const result = await invoke<{ status: number; body: unknown }>("hub_api", {
    method: req.method,
    path: `${req.path}${query ? `?${query}` : ""}`,
    body: req.body ?? null,
  });
  return { status: result.status, body: result.body };
};

export const hubClient = createHubClient({
  baseUrl: HUB_SITE,
  transport,
});
