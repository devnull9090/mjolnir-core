import { NextResponse } from "next/server";

export const revalidate = 60; // Cache for 60 seconds

const CHECKSUMS_URL = "https://releases.mjolnircore.com/launcher/latest/checksums.txt";

interface Artifact {
  name: string;
  hash: string;
}

/**
 * What a launcher release's checksums.txt says: the version from its
 * header line, and each installer's file name and SHA-256. Releases stopped
 * shipping an MSI, so `msi` is null for every current one.
 */
function parseChecksums(text: string): {
  version: string | null;
  msi: Artifact | null;
  nsis: Artifact | null;
} {
  let version: string | null = null;
  let msi: Artifact | null = null;
  let nsis: Artifact | null = null;
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      const verMatch = trimmed.match(/v(\d+\.\d+\.\d+)/);
      if (verMatch) version = verMatch[1];
      continue;
    }
    const parts = trimmed.split(/\s+/);
    if (parts.length >= 2) {
      const [hash, name] = parts;
      if (name.endsWith(".msi")) msi = { name, hash };
      else if (name.endsWith(".exe")) nsis = { name, hash };
    }
  }
  return { version, msi, nsis };
}

/**
 * No release to describe. This used to answer with a made-up 0.3.0 instead,
 * which the updater read as "up to date" and the download page as a real
 * release; an error makes the launcher say it could not check.
 */
function unavailable(message: string) {
  return NextResponse.json(
    { error: "unavailable", message },
    { status: 503, headers: { "Cache-Control": "no-store" } },
  );
}

export async function GET() {
  let text: string;
  try {
    // Fetch checksums for hashes and version info
    const res = await fetch(CHECKSUMS_URL, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return unavailable(`The launcher's checksums.txt answered ${res.status}.`);
    text = await res.text();
  } catch (err) {
    console.error("Failed to fetch latest checksums:", err);
    return unavailable("The launcher's checksums.txt could not be fetched.");
  }

  const { version, msi, nsis } = parseChecksums(text);
  if (!version || !nsis) {
    return unavailable("The launcher's checksums.txt names no version or setup installer.");
  }

  // Everything below is served from the immutable per-release directory
  // rather than from latest/.
  //
  // latest/ is a mutable key behind a 4-hour CDN cache, so for hours after a
  // release the binary served there can still be the previous version while
  // this endpoint already advertises the new signature. The updater then
  // downloads bytes that its signature does not cover and refuses the update.
  // Discovery still reads latest/checksums.txt — a stale read there only
  // delays the announcement, because version, signature and binary are then
  // all taken from that same release and cannot disagree with each other.
  const releaseDir = `https://releases.mjolnircore.com/launcher/launcher-v${version}`;
  const nsisUrl = `${releaseDir}/${nsis.name}`;

  // Fetch the NSIS signature for Tauri updater verification
  let nsisSignature = "";
  try {
    const sigRes = await fetch(`${nsisUrl}.sig`, {
      next: { revalidate: 60 },
    });
    if (sigRes.ok) {
      nsisSignature = await sigRes.text();
    }
  } catch (err) {
    console.error("Failed to fetch signature:", err);
  }

  return NextResponse.json({
    // Standard metadata for web UI & checksum viewer
    version,
    notes: `MJOLNIR Launcher v${version} release.`,
    pub_date: new Date().toISOString(),
    // Null unless the release ships an MSI, which none has since the MSI
    // was dropped; a name and URL here would point at a file that is not there.
    msi_name: msi?.name ?? null,
    msi_hash: msi?.hash ?? null,
    msi_url: msi ? `${releaseDir}/${msi.name}` : null,
    nsis_name: nsis.name,
    nsis_hash: nsis.hash,
    nsis_url: nsisUrl,
    checksums_url: CHECKSUMS_URL,
    // Tauri v2 plugin-updater format
    platforms: {
      "windows-x86_64": {
        signature: nsisSignature,
        url: nsisUrl,
      },
    },
  });
}
