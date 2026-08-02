import { NextResponse } from "next/server";

export const revalidate = 60; // Cache for 60 seconds

export async function GET() {
  let msiHash: string | null = null;
  let msiName = "MJOLNIR-Launcher_0.3.0_x64_en-US.msi";
  let nsisHash: string | null = null;
  let nsisName = "MJOLNIR-Launcher_0.3.0_x64-setup.exe";
  let version = "0.3.0";
  let nsisSignature = "";

  try {
    // Fetch checksums for hashes and version info
    const res = await fetch("https://releases.mjolnircore.com/launcher/latest/checksums.txt", {
      next: { revalidate: 60 },
    });
    if (res.ok) {
      const text = await res.text();
      for (const line of text.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#")) {
          const verMatch = trimmed.match(/v(\d+\.\d+\.\d+)/);
          if (verMatch) version = verMatch[1];
          continue;
        }
        const parts = trimmed.split(/\s+/);
        if (parts.length >= 2) {
          const hash = parts[0];
          const filename = parts[1];
          if (filename.endsWith(".msi")) {
            msiHash = hash;
            msiName = filename;
          } else if (filename.endsWith(".exe")) {
            nsisHash = hash;
            nsisName = filename;
          }
        }
      }
    }
  } catch (err) {
    console.error("Failed to fetch latest checksums:", err);
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
  const nsisUrl = `${releaseDir}/${nsisName}`;
  const msiUrl = `${releaseDir}/${msiName}`;

  // Fetch the NSIS signature for Tauri updater verification
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
    msi_name: msiName,
    msi_hash: msiHash,
    msi_url: msiUrl,
    nsis_name: nsisName,
    nsis_hash: nsisHash,
    nsis_url: nsisUrl,
    checksums_url: "https://releases.mjolnircore.com/launcher/latest/checksums.txt",
    // Tauri v2 plugin-updater format
    platforms: {
      "windows-x86_64": {
        signature: nsisSignature,
        url: nsisUrl,
      },
    },
  });
}
