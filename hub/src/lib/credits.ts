/**
 * Everything MJOLNIR Core ships, builds with or learned from that somebody
 * else made: the one list behind /credits.
 *
 * KEEPING IT UP TO DATE (docs/credits.md has the full rules):
 *
 * - Add an entry in the same change that brings the thing in: a content pack
 *   in unreal/MJOLNIRMaterials, a vendored binary, ported code, a new
 *   dependency a shipped product is built on, a community map or pack whose
 *   author is not its hub uploader.
 * - A pack whose assets cook into something we publish also gets its
 *   `/Game/...` folder in `contentPaths`. `pnpm test` (scripts/test-credits.mts)
 *   fails when tools/level/foliage_bake.py names a pack folder no entry
 *   here claims, and when an entry is missing a field its licence needs.
 * - State what the licence says, not what we hope: copy the name from the
 *   project's own LICENSE or store page, and link it.
 * - `status: "planned"` is for something in the tree that no release
 *   carries yet. Change it to "shipped" in the release that first carries it.
 */

export type CreditStatus = "shipped" | "planned";

export interface Credit {
  /** What it is called by its makers. */
  name: string;
  /** Who made it. */
  by: string;
  /** Its own page: the project, the listing, the repository. */
  url: string;
  /** The licence's name as its makers give it. */
  licence: string;
  /** The licence text, when there is a canonical page for it. */
  licenceUrl?: string;
  /** What we use it for, in a sentence a player can read. */
  use: string;
  /** Changes we made, where the licence asks that they be stated. */
  changes?: string;
  /** Our own derived work, when it is public: a port, a patch set. */
  derived?: { label: string; url: string };
  /** `/Game/...` folders of a content pack whose assets we cook and ship. */
  contentPaths?: string[];
  status: CreditStatus;
}

export interface CreditSection {
  id: string;
  title: string;
  blurb: string;
  entries: Credit[];
}

const MIT = "https://opensource.org/license/mit";
const APACHE = "https://www.apache.org/licenses/LICENSE-2.0";

export const CREDIT_SECTIONS: CreditSection[] = [
  {
    id: "assets",
    title: "Art and asset packs",
    blurb:
      "Models, textures and materials made by others that are cooked into maps we publish. The game's own assets are not listed: maps refer to those, they do not carry them.",
    entries: [
      {
        name: "Namaqualand Environment and Asset Pack",
        by: "Poly Haven",
        url: "https://www.fab.com/listings/295ed897-fe78-4711-a583-d9b80fde554a",
        licence: "Creative Commons Attribution 4.0 International (CC BY 4.0)",
        licenceUrl: "https://creativecommons.org/licenses/by/4.0/",
        use: "Flowers, succulents, rooibos bushes and granite stones in the desert dressing of the remastered Coagulation, and the ice plants and succulents on the dunes of the remastered Zanzibar.",
        changes:
          "Textures capped at 1024 pixels; meshes re-encoded for Halo Campaign Evolved; scaled and scattered by our own rules.",
        contentPaths: ["/Game/Namaqualand/"],
        status: "planned",
      },
      {
        name: "Poly Haven textures: Concrete Wall 008, Concrete Wall 006, Metal Plate 02, Corrugated Iron 02 and Rusty Metal Sheet",
        by: "Poly Haven",
        url: "https://polyhaven.com/textures",
        licence: "CC0 1.0 Universal (public domain dedication)",
        licenceUrl: "https://creativecommons.org/publicdomain/zero/1.0/",
        use: "The concrete and weathered steel that the walls, floors and machinery of the remastered Zanzibar are drawn in.",
        changes:
          "Used at 2048 pixels; ambient occlusion, roughness and height packed into one map; blended with each wall's original Halo 2 colour map.",
        status: "planned",
      },
    ],
  },
  {
    id: "runtime",
    title: "Software we ship",
    blurb: "Other people's programs and code that are inside our downloads.",
    entries: [
      {
        name: "UE4SS (RE-UE4SS)",
        by: "the UE4SS-RE contributors",
        url: "https://github.com/UE4SS-RE/RE-UE4SS",
        licence: "MIT License",
        licenceUrl: MIT,
        use: "The script host every MJOLNIR mod runs on. The launcher installs a pinned build of it.",
        status: "shipped",
      },
      {
        name: "CUE4Parse",
        by: "the CUE4Parse contributors",
        url: "https://github.com/FabianFG/CUE4Parse",
        licence: "Apache License 2.0",
        licenceUrl: APACHE,
        use: "Our Nanite mesh decoder is a Rust port of its Nanite readers, for Unreal Engine 5.5 only. It is one module of our own code, not a fork of the project.",
        changes: "Rewritten in Rust; see the NOTICE file in the repository.",
        derived: {
          label: "Our port: crates/ue-asset/src/nanite.rs",
          url: "https://github.com/devnull9090/mjolnir-core/blob/main/crates/ue-asset/src/nanite.rs",
        },
        status: "shipped",
      },
      {
        name: "oozextract",
        by: "lvlvllvlvllvlvl",
        url: "https://github.com/lvlvllvlvllvlvl/oozextract",
        licence: "MIT License",
        licenceUrl: MIT,
        use: "Decompresses the game's Oodle-packed containers in our tools.",
        status: "shipped",
      },
      {
        name: "Tauri",
        by: "the Tauri Programme within the Commons Conservancy",
        url: "https://tauri.app",
        licence: "MIT License or Apache License 2.0",
        use: "The launcher and the tag editor are Tauri apps.",
        status: "shipped",
      },
      {
        name: "React",
        by: "Meta Platforms and contributors",
        url: "https://react.dev",
        licence: "MIT License",
        licenceUrl: MIT,
        use: "The interface of the launcher, the tag editor and this site.",
        status: "shipped",
      },
      {
        name: "three.js",
        by: "the three.js authors",
        url: "https://threejs.org",
        licence: "MIT License",
        licenceUrl: MIT,
        use: "The 3D map previews on this site and the model viewer in the tag editor.",
        status: "shipped",
      },
      {
        name: "Tailwind CSS",
        by: "Tailwind Labs",
        url: "https://tailwindcss.com",
        licence: "MIT License",
        licenceUrl: MIT,
        use: "Styling in the launcher, the tag editor and this site.",
        status: "shipped",
      },
      {
        name: "Rust crates",
        by: "their authors",
        url: "https://github.com/devnull9090/mjolnir-core/blob/main/Cargo.lock",
        licence: "MIT, Apache 2.0, ISC, CC0 and similar; each crate's own",
        use: "The CLI and the native parts of the launcher and tag editor are built on serde, clap, anyhow, blake3, flate2, memmap2, libloading and the crates they depend on. Cargo.lock lists every one.",
        status: "shipped",
      },
    ],
  },
  {
    id: "site",
    title: "This site",
    blurb: "What mjolnircore.com is built with.",
    entries: [
      {
        name: "Next.js",
        by: "Vercel and contributors",
        url: "https://nextjs.org",
        licence: "MIT License",
        licenceUrl: MIT,
        use: "The site's framework.",
        status: "shipped",
      },
      {
        name: "OpenNext for Cloudflare",
        by: "the OpenNext contributors",
        url: "https://opennext.js.org/cloudflare",
        licence: "MIT License",
        licenceUrl: MIT,
        use: "Runs the site on Cloudflare Workers.",
        status: "shipped",
      },
      {
        name: "Hono",
        by: "Yusuke Wada and contributors",
        url: "https://hono.dev",
        licence: "MIT License",
        licenceUrl: MIT,
        use: "The hub's API.",
        status: "shipped",
      },
      {
        name: "Zod",
        by: "Colin McDonnell and contributors",
        url: "https://zod.dev",
        licence: "MIT License",
        licenceUrl: MIT,
        use: "Checks every request and response of the API.",
        status: "shipped",
      },
      {
        name: "Lucide",
        by: "the Lucide contributors",
        url: "https://lucide.dev",
        licence: "ISC License",
        licenceUrl: "https://lucide.dev/license",
        use: "The icons.",
        status: "shipped",
      },
      {
        name: "Geist and Geist Mono",
        by: "Vercel with Basement Studio",
        url: "https://vercel.com/font",
        licence: "SIL Open Font License 1.1",
        licenceUrl: "https://openfontlicense.org",
        use: "The typefaces.",
        status: "shipped",
      },
      {
        name: "react-markdown, remark-gfm, rehype-slug and fflate",
        by: "their authors",
        url: "https://github.com/devnull9090/mjolnir-core/blob/main/hub/package.json",
        licence: "MIT License",
        licenceUrl: MIT,
        use: "Render the docs, the blog and the changelog, and read uploaded archives.",
        status: "shipped",
      },
    ],
  },
  {
    id: "tools",
    title: "Tools we build with",
    blurb: "Not in any download, but none of this would exist without them.",
    entries: [
      {
        name: "Unreal Engine 5.5",
        by: "Epic Games",
        url: "https://www.unrealengine.com",
        licence: "Unreal Engine End User License Agreement",
        licenceUrl: "https://www.unrealengine.com/eula",
        use: "Cooks the materials, landscapes and meshes of the remastered maps.",
        status: "shipped",
      },
      {
        name: "Upscayl and Real-ESRGAN",
        by: "the Upscayl team; Xintao Wang and the Real-ESRGAN contributors",
        url: "https://github.com/upscayl/upscayl",
        licence: "AGPL-3.0 (Upscayl); BSD 3-Clause (Real-ESRGAN)",
        use: "Enlarges the remastered Zanzibar's one-off textures (hazard stripes, signs, the wheel and crane, props) four times, from Halo 2's originals.",
        status: "planned",
      },
      {
        name: "GPT Image 2.6",
        by: "OpenAI",
        url: "https://developers.openai.com/api/docs/guides/image-generation",
        licence: "OpenAI Services Agreement",
        licenceUrl: "https://openai.com/policies/services-agreement/",
        use: "Redraws signs too small for an upscaler to read (the remastered Zanzibar's 64 by 32 pixel notice), from Halo 2's original and the words on it.",
        status: "planned",
      },
      {
        name: "Ghidra",
        by: "the National Security Agency and contributors",
        url: "https://ghidra-sre.org",
        licence: "Apache License 2.0",
        licenceUrl: APACHE,
        use: "Reading how the game works, for research and interoperability.",
        status: "shipped",
      },
      {
        name: "Blender",
        by: "the Blender Foundation and contributors",
        url: "https://www.blender.org",
        licence: "GNU General Public License v3 or later",
        licenceUrl: "https://www.blender.org/about/license/",
        use: "Authoring and checking map geometry.",
        status: "shipped",
      },
    ],
  },
  {
    id: "learned-from",
    title: "Packs we studied",
    blurb:
      "Free packs we read for technique. Nothing from them is in any download; they are listed so the debt is on record.",
    entries: [
      {
        name: "Landscape Pro 2.0 Auto-Generated Material",
        by: "STF3d",
        url: "https://www.fab.com/listings/1ac647da-b1bc-4e72-a56d-60aaeb6918e1",
        licence: "Fab Standard License",
        licenceUrl: "https://www.fab.com/eula",
        use: "How it ties a plant mix to each ground layer and culls its smallest pieces close.",
        status: "planned",
      },
      {
        name: "Procedural Nature Pack Vol.1",
        by: "PurePolygons",
        url: "https://www.fab.com/listings/d3a29766-c848-40c5-ad3d-d609b80d224b",
        licence: "Fab Standard License",
        licenceUrl: "https://www.fab.com/eula",
        use: "Its description of slope-driven river speed and foam; the pack itself was not opened.",
        status: "planned",
      },
    ],
  },
];

/** Every entry, for checks and counts. */
export function allCredits(): Credit[] {
  return CREDIT_SECTIONS.flatMap((s) => s.entries);
}
