import { NextResponse } from "next/server";

export const revalidate = 60; // Cache for 60 seconds

export async function GET() {
  let msiHash: string | null = null;
  let msiName = "MJOLNIR-Launcher_0.1.0_x64_en-US.msi";
  let nsisHash: string | null = null;
  let nsisName = "MJOLNIR-Launcher_0.1.0_x64-setup.exe";
  let version = "0.1.0";

  try {
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

  return NextResponse.json({
    version,
    msi_name: msiName,
    msi_hash: msiHash,
    msi_url: `https://releases.mjolnircore.com/launcher/latest/${msiName}`,
    nsis_name: nsisName,
    nsis_hash: nsisHash,
    nsis_url: `https://releases.mjolnircore.com/launcher/latest/${nsisName}`,
    checksums_url: "https://releases.mjolnircore.com/launcher/latest/checksums.txt",
    updated_at: new Date().toISOString(),
  });
}
