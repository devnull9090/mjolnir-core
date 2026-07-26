import { NextResponse } from "next/server";

// GET /api/releases/latest - Latest launcher version info (for auto-update)
export async function GET() {
  return NextResponse.json({
    version: "1.0.0",
    date: "2026-07-25",
    download_url: "https://releases.mjolnircore.com/launcher/mjolnir-launcher-v1.0.0-windows-x64.msi",
    changelog: "Initial release — mod management, game launcher, auto-update",
    checksum_sha256: null,
  });
}
