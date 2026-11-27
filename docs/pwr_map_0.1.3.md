# Pelican Warfare map 0.1.3: how it was built

Map 0.1.3 is the 0.1.2 candidate ([pwr_map_0.1.2.md](pwr_map_0.1.2.md)) with one change,
built on 2026-11-26 and not yet released: **the distant mountain ring is split into 12
sectors** the engine can cull. It was one 3.24M-triangle mesh whose bounds always held
the camera, so it was drawn whole every frame. On a GTX 1080 Ti that cost 1.7-2.7 ms
looking out from the centre and 0.9 ms looking at the ground; split, both are about
0.2 ms. From a base looking across the map nothing changes: most of the range is in
view there. Method and measurements: `levels/warfare/pwr/visual_dressing/README.md`,
"Splitting the apron into sectors".

0.1.2 has not shipped either. Players on 0.1.1 get both sets of changes with 0.1.3.

## Inputs, pinned by hash

| Input | SHA-256 |
|---|---|
| 0.1.2 candidate pack, `out/pwr-rebuild/pelican-warfare-0.1.2.mjolnir` | `960439d2…fdf765` |
| Its map input, `out/pwr-rebuild/map-input-final` (chunk 963 `.ucas`) | `3356891e…544231` |
| The ring it split, `apron-v9b` in the pelican-warfare Codex worktree (same `.ucas`) | `3356891e…544231` |
| The split, `out/pwr/apron-sectors-12c` (`.ucas` / `.utoc`) | `a75ea1f9…d59936e5` / `fa7d762c…16a68349` |

The old chunk 963 holds one package (`SM_PWR_DistantApron`); the new one holds its 12
sectors (`SM_PWR_DistantApron_S00`-`S11`) and nothing else, so replacing the container
drops nothing.

## Steps

1. **Split** (as in the README): `split_apron.py --apron-dir <apron-v9b> --out
   out/pwr/apron-sectors-12c --sectors 12`, with `mesh_rewrite` and `package_add` built
   from this branch.
2. **Map input** `out/pwr-rebuild/map-input-0.1.3`: every member of
   `map-input-final` hard-linked except chunk 963 (the split's `.utoc`/`.ucas` copied under
   the input's name, `pakchunk963-MJOLNIRPWRVISTA-PWR_P`) and `pwr.level.json`. In the level
   file the one row drawing `SM_PWR_DistantApron` (the mesh `visual_dressing/vista.json`
   names) becomes 12 rows, exactly as `stage_vista.py` does it: each keeps that row's
   materials and values and takes id, mesh, position and scale from the split's
   `runtime_decor.json`. Sector 0 keeps the id `pwr_distant_apron`. 1,105 decor rows
   become 1,116.
3. **Pack**: `mjolnir map pack --code PWR --version 0.1.3 --slug pelican-warfare --game
   halo1 --size large --players 2-16 --vehicles true --runtime "^1.24.0" --summary <0.1.2's>
   --sign`, the same metadata as 0.1.2 (the pack's `mjolnir.json` differs only in its
   version).
4. **Loss check**: `release_loss.py` against the 0.1.2 candidate: nothing lost. Members
   changed: chunk 963 (`.utoc`, `.ucas`), `map/level.json`, and the pack's own
   `mjolnir.json` and `signature.json`.

Output: `out/pwr-rebuild/pelican-warfare-0.1.3.mjolnir` (not in git), SHA-256
`70627803…e1fdf765`, 690 MB.

## Ship the two together

The level file and chunk 963 must ship together. A new level file over an old chunk 963
names 12 meshes that are not there, and draws no mountains. An old level file over the
new chunk 963 names the one mesh that is gone, with the same result. The pack carries
both, so a normal install is safe; never copy one without the other.

## Proven, and not yet

Proven on PC3 (GTX 1080 Ti) with the split container mounted as a test chunk under a
level file staged the same way: the timings above, the range whole from 12 headings at
300 m, and no seams or lighting steps across the sector joins.

Not yet: this pack installed as a whole (`mjolnir dev install`) and played, on any PC;
a two-PC match on it.
