/**
 * Writes the OpenAPI 3.1 document to public/openapi.json.
 *
 * The committed copy exists so the spec is diffable in review and CI can
 * fail when it drifts from the code (`pnpm openapi:check`). The live
 * endpoint at /api/v1/openapi.json is generated from the same app object,
 * so the two cannot disagree once this file is up to date.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { app, openApiInfo } from "../src/lib/api/app";

const doc = app.getOpenAPI31Document(openApiInfo);
const out = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "openapi.json");
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(doc, null, 2) + "\n");
console.log(`wrote ${out}`);
