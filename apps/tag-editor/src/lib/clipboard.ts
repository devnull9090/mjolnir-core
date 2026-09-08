/** Copy text, falling back to the selection dance where the async API is
 *  unavailable (an http dev origin, an older webview). */
export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    // Fall through.
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    document.execCommand("copy");
  } catch {
    // Out of options; the click simply does nothing.
  }
  area.remove();
}
