import { NextResponse } from "next/server";

// GET /api/mods - List all mods
export async function GET(request: Request) {
  const url = new URL(request.url);
  const category = url.searchParams.get("category");
  const search = url.searchParams.get("q");
  const page = parseInt(url.searchParams.get("page") || "1");
  const limit = parseInt(url.searchParams.get("limit") || "20");
  const offset = (page - 1) * limit;

  // In production, this queries D1 via the env binding
  // For now, return static data until wrangler bindings are wired
  const mods = [
    { id: "1", slug: "mjolnir-flycam", name: "MJOLNIRFlyCam", description: "Free debug camera", author: "devnull9090", version: "1.0.0", category: "camera", downloads: 0, created_at: new Date().toISOString() },
    { id: "2", slug: "mjolnir-console-enabler", name: "MJOLNIRConsoleEnabler", description: "UE5 console enabler", author: "devnull9090", version: "1.0.0", category: "tools", downloads: 0, created_at: new Date().toISOString() },
    { id: "3", slug: "mjolnir-multiplayer", name: "MJOLNIRMultiplayer", description: "Experimental map travel & admin", author: "devnull9090", version: "0.1.0", category: "multiplayer", downloads: 0, created_at: new Date().toISOString() },
    { id: "4", slug: "mjolnir-core", name: "MJOLNIRCore", description: "Core runtime & UEHelpers", author: "devnull9090", version: "1.0.0", category: "framework", downloads: 0, created_at: new Date().toISOString() },
    { id: "5", slug: "mjolnir-discovery", name: "MJOLNIRDiscovery", description: "UFunction diagnostics", author: "devnull9090", version: "0.1.0", category: "tools", downloads: 0, created_at: new Date().toISOString() },
  ];

  let filtered = mods;
  if (category && category !== "all") {
    filtered = filtered.filter((m) => m.category === category);
  }
  if (search) {
    const q = search.toLowerCase();
    filtered = filtered.filter((m) => m.name.toLowerCase().includes(q) || m.description.toLowerCase().includes(q));
  }

  return NextResponse.json({
    mods: filtered.slice(offset, offset + limit),
    total: filtered.length,
    page,
    limit,
  });
}
