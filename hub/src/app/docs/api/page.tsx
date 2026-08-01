import type { Metadata } from "next";

import { ScalarDocs } from "./ScalarDocs";

export const metadata: Metadata = {
  title: "API Reference | MJOLNIR Core",
  description:
    "The open MJOLNIR Hub API: browse mods, releases, and conflict data. " +
    "OpenAPI 3.1 spec available at /api/v1/openapi.json.",
};

export default function ApiReferencePage() {
  return (
    <div className="px-2 py-6 md:px-6">
      <div className="mb-6">
        <h1 className="mb-2 text-3xl font-black text-foreground">API Reference</h1>
        <p className="text-text-muted">
          The hub&apos;s API is open: reads need no authentication, and the spec is
          machine-readable at{" "}
          <a href="/api/v1/openapi.json" className="text-gold hover:underline">
            /api/v1/openapi.json
          </a>{" "}
          for third-party tools.
        </p>
      </div>
      <ScalarDocs specUrl="/api/v1/openapi.json" />
    </div>
  );
}
