"""Seal .37 alluvium against the four verified .36 landscape and gameplay members."""

import json
import shutil
import package_pwr_headwater as p

base = p.ROOT / "out/pwr/river-apron"
work = base / "finish37"
prior = base / "native/map-input"
assets = {
    f"MJOLNIR/GrassPilot/Playable/{name}.uasset"
    for name in ("SM_PWR_OutletAlluvium", "M_PWR_OutletAlluvium")
}
parent_sha = "dffdab938df584eae87ea0ca84b22dad7b098e4ab76f23ad08848066f01b9ca4"


def main():
    p.out = work
    p.n = work / "native"
    p.maps = work / "map-input"
    p.old = prior
    p.apron = False
    p.n.mkdir(exist_ok=True)
    parent = base / "saturday.36/pelican-warfare-0.1.0-playtest.36.mjolnir"
    if p.sha(parent) != parent_sha:
        raise ValueError("Unrecognised .36 parent")
    old = json.loads((base / "native/landscape-collision.json").read_text())
    for name, expected in old["native_members"].items():
        if p.sha(prior / name) != expected:
            raise ValueError("Unrecognised .36 native member " + name)
    checked = json.loads((work / "editor-verified.json").read_text())
    if (
        checked["mesh"]["support_sha256"] != old["outlet_surface"]["support_sha256"]
        or checked["mesh"]["surface_sha256"] != p.sha(work / "surface.json")
        or checked["vegetation"] != p.sha(work / "vegetation.json")
    ):
        raise ValueError("Unverified art")
    p.prepare(allowed_additions=assets)
    land = json.loads((p.n / "land-diff.json").read_text())
    if not assets <= set(land) or any(v[0] is None for v in land.values()):
        raise ValueError("Asset identity changed")
    bsp = base / "native/physics/pwr.sbsp"
    if p.sha(bsp) != old["sbsp"]:
        raise ValueError("Original physics changed")
    world = p.n / "world-bake"
    p.run(
        [
            p.cli,
            "level",
            "bake",
            base / "native/native-level.json",
            "--paks",
            p.paks,
            "--standalone",
            "PWR",
            "--bsp",
            "8=" + str(bsp.resolve()),
            "--out-dir",
            world,
            "--world",
            p.n / "LPE.umap",
        ],
        p.n / "world-bake.log",
    )
    toc = p.WORLD + ".utoc"
    diff = p.changes(prior / toc, world / toc)
    if not diff or not all(
        k.endswith(("/PWR/PWR.umap", "/PWR/PWR.ubulk")) for k in diff
    ):
        raise ValueError("Unrelated gameplay change " + str(list(diff)))
    for ext in (".utoc", ".ucas"):
        shutil.copyfile(world / (p.WORLD + ext), p.maps / (p.WORLD + ext))
    sealed = {file.name: p.sha(file) for file in p.maps.iterdir()}
    if set(sealed) != set(old["native_members"]):
        raise ValueError("Unexpected release input inventory")
    proof = dict(
        parent_map_sha256=parent_sha,
        native_members=sealed,
        parent_native_members=old["native_members"],
        retained_bsp_sha256=old["sbsp"],
        retained_terrain_sha256=old["terrain_manifest_sha256"],
        retained_dressing_ledger_sha256=old["dressing_ledger_sha256"],
        editor_readback=checked,
        changed_source_art=[
            "Rounded, individually tinted bankside cobbles, bed stones, ragged sod and root shading",
            "Location-registered photographed channel sediment and local rock material",
            "Seven stock plant groups, changed only around the two surveyed banks",
        ],
        land_changed=land,
        world_changed=diff,
        survey=json.loads((work / "survey.json").read_text()),
        build="levels/warfare/pwr/build_outlet_finish.ps1",
    )
    tmp = work / "receipt.pending"
    tmp.write_text(json.dumps(proof, indent=2) + "\n")
    tmp.replace(work / "receipt.json")
    print(
        json.dumps(
            dict(native_members=sealed, land=list(land), world=list(diff)), indent=2
        )
    )


if __name__ == "__main__":
    main()
