// Run from the repo root: node assets/discord/render.mjs
// Uses the hub's existing Puppeteer dependency. An optional first argument can
// name another hub checkout containing node_modules for a worktree render.
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import { stat } from "node:fs/promises";

const here = path.dirname(fileURLToPath(import.meta.url));
const hub = path.resolve(process.argv[2] || path.join(here, "../../hub"));
const require = createRequire(path.join(hub, "package.json"));
const puppeteer = require("puppeteer");
const browser = await puppeteer.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1024, height: 576, deviceScaleFactor: 1 });
  for (const variant of ["background", "cover"]) {
    const url = pathToFileURL(path.join(here, "activity.html"));
    url.searchParams.set("variant", variant);
    await page.goto(url.href, { waitUntil: "networkidle0" });
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all([...document.images].map(img => img.decode()));
    });
    const output = path.join(here, `mjolnir-core-${variant}.png`);
    await page.screenshot({ path: output, type: "png", clip: { x: 0, y: 0, width: 1024, height: 576 } });
    const { size } = await stat(output);
    if (size >= 10_000_000) throw new Error(`${output} exceeds Discord's size limit`);
    console.log(`${output}: 1024x576, ${size} bytes`);
  }
} finally {
  await browser.close();
}
