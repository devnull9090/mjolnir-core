import { NextResponse } from "next/server";

// Deep import, not the `@mjolnir/hub-kit` barrel: that barrel re-exports the
// shared React components, which carry no "use client" directive (the website
// adds the boundary in app/components/HubKit.tsx), so pulling it into a server
// route drags `useState` into a Server Component and fails the build.
import { compareVersions } from "@mjolnir/hub-kit/ui/format";
import { getProducts, getReleases } from "@/lib/changelog";

/**
 * The published changelog, for everything that is not this website.
 *
 * The launcher and the tag editor show release notes after they update
 * themselves, and they read them from here rather than embedding a copy —
 * so an entry corrected after a release reaches every surface.
 *
 * It sits outside /api/v1 alongside /api/releases/latest, for the same reason:
 * this is release metadata, not part of the versioned hub API that mods and
 * accounts live behind. It is public, unauthenticated and read-only.
 *
 * Query parameters:
 *   product  only this product's releases
 *   since    only releases newer than this version (requires product)
 *   limit    newest N, 1-200
 */

// The data is baked into the build, so a response can only change when the
// site is redeployed. An hour is short enough that a corrected entry lands
// promptly and long enough that a launcher fleet checking on startup is not
// re-rendering this constantly.
export const revalidate = 3600;

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const product = params.get("product");
  const since = params.get("since");
  const limitParam = params.get("limit");

  const products = getProducts();

  if (product && !products.some((p) => p.id === product)) {
    return NextResponse.json(
      {
        error: "unknown_product",
        message: `No product "${product}".`,
        known: products.map((p) => p.id),
      },
      { status: 404 },
    );
  }

  if (since && !product) {
    return NextResponse.json(
      {
        error: "since_requires_product",
        message: "`since` compares versions, which are only ordered within one product.",
      },
      { status: 400 },
    );
  }

  let releases = getReleases();
  if (product) releases = releases.filter((r) => r.product === product);
  if (since) releases = releases.filter((r) => compareVersions(r.version, since) > 0);

  if (limitParam !== null) {
    const limit = Number.parseInt(limitParam, 10);
    if (!Number.isFinite(limit) || limit < 1 || limit > 200) {
      return NextResponse.json(
        { error: "bad_limit", message: "`limit` must be between 1 and 200." },
        { status: 400 },
      );
    }
    releases = releases.slice(0, limit);
  }

  return NextResponse.json(
    { products, releases },
    {
      headers: {
        // Read by desktop apps from a different origin.
        "access-control-allow-origin": "*",
        "cache-control": "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400",
      },
    },
  );
}
