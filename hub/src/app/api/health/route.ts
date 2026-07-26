import { NextResponse } from "next/server";

// GET /api/health - Health check
export async function GET() {
  return NextResponse.json({
    status: "ok",
    service: "mjolnir-hub",
    version: "0.1.0",
    timestamp: new Date().toISOString(),
  });
}
