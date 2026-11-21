"""Compare the outlet from fixed Halo bridge cameras and restore the shared install."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

WORK = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("river_review", WORK.parent / "river-erosion/rehearse.py")
river = importlib.util.module_from_spec(spec)
spec.loader.exec_module(river)

previous, b, v = river.previous, river.b, river.v
BASE = previous.BENCH / "river-shore-35/water"


def sample_outlet(photo, pose, native_dir, output):
    photo.setpose(pose, True)
    b.prove_pose(photo, pose)
    code = (b.HERE / "window.lua").read_text(encoding="utf-8-sig")
    dll = native_dir / "mjolnir_frame_times.dll"
    code = code.replace("__DLL__", json.dumps(dll.as_posix()))
    code = code.replace("__TIMES__", json.dumps((native_dir / "frame_times.txt").as_posix()))
    b.check("BENCH_READY" in b.run_lua(photo, code), "Native frame timer unavailable")
    try:
        time.sleep(8)
        samples = [b.take_window(photo) for _ in range(3)]
        b.prove_pose(photo, pose)
        b.write(output / "native-performance.json", dict(camera=pose, settings=b.checked_settings(photo),
                module_sha256=b.sha(dll), windows=samples, aggregate=b.aggregate(samples)))
    finally:
        b.run_lua(photo, b.STOP)


def run(folder, identity, pid, photo, native):
    photo.runlua = lambda code: b.run_lua(photo, code)
    photo.private_world()
    lobby = photo.get_lobby()
    b.check(lobby.get("world") == "PWR" and lobby.get("players") == "1" and lobby.get("public") == "0", "Private PWR required")
    photo.dressing()
    settings = b.checked_settings(photo)
    baseline = b.read(BASE / "photos.json")
    cameras = baseline["views"].copy()
    b.check(settings == baseline["settings"], "Camera profile differs from the previous playtest")
    output = folder / "water"
    output.mkdir()
    frames = {}

    def photograph(name, pose):
        photo.setpose(pose, True)
        time.sleep(2.8)
        frames[name] = v.take_image(photo, output, name, pose)

    def probe(name, source, marker):
        raw = b.run_lua(photo, source)
        (output / (name + ".log")).write_text(raw, encoding="utf8")
        b.check(marker in raw, name + " readback failed: " + raw[-500:])

    try:
        b.run_lua(photo, photo.PREP + photo.HIDE)
        if args.edge_trial:
            lua = river.ROOT / "levels/warfare/pwr/terrain/trial_river_edge.lua"
            cameras = {"overhead": cameras["seam-overhead"], "low": previous.pose((-47,-27,99),(-36,-7.8,92.2),65)}
            try:
                probe("edge-setup", lua.read_text(), "PWR_EDGE_READY PASS")
                for mode in ("control", "uv", "cm", "hide"):
                    if mode != "control":
                        probe("edge-" + mode, "PWREdgeStudy.apply('" + mode + "')", "PWR_EDGE")
                    for key, pose in cameras.items():
                        photograph(mode + "-" + key, pose)
            finally:
                probe("edge-restored", "if PWREdgeStudy then PWREdgeStudy.restore() end", "PWR_EDGE_RESTORED PASS")
        elif args.performance_control:
            for name in ("outlet", "riffle", "waterline", "basin", "east-bank", "seam-overhead", "river-seam"):
                photo.setpose(cameras[name], True)
                time.sleep(2.8)
            sample_outlet(photo, cameras["outlet"], native, output)
        else:
            for name in ("outlet", "riffle", "waterline", "basin", "east-bank", "seam-overhead", "river-seam"):
                photograph(name, cameras[name])
            b.write(output / "photos.json", dict(release=identity, settings=settings, views=cameras, frames=frames))
            photo.setpose(cameras["outlet"], True)
            time.sleep(5)
            start = previous.sample_clock(photo)
            time.sleep(15)
            end = previous.sample_clock(photo)
            count, seconds = end[0] - start[0], end[1] - start[1]
            b.check(count > 0 and 14.8 < seconds < 30, "Invalid outlet timing")
            b.write(output / "outlet-performance.json", dict(frames=count, seconds=seconds, fps=count/seconds,
                    settings=b.checked_settings(photo), camera=cameras["outlet"]))
            contact_finish = identity["archive"].endswith(".39.mjolnir")
            candidate_work = WORK.parent / "river-basin" if contact_finish or identity["archive"].endswith(".38.mjolnir") else WORK
            field = river.load_heightfield(candidate_work / "terrain/runtime-master.json")
            survey = b.read(WORK / "dressing/apron-survey.json")
            locations = {name: station["xy_m"] for name, station in survey["native_probes"].items()}
            locations["lakebed"] = [-352, 893]
            if candidate_work != WORK:
                locations.update(b.read(candidate_work / "terrain/basin-probes.json")["terrain_probes"])
            probe("terrain", river.terrain_probe(field, locations), "HEADWATER_LANDSCAPE_ACCEPTANCE PASS")
            water_dir = candidate_work / "shore-contact/water-fix" if contact_finish else candidate_work / "water-fix"
            probe("water", (water_dir / "river_flux_readback.lua").read_text(), "HEADWATER_TEXEL_ACCEPTANCE PASS")
            probe("painter", (river.WORK / "junction/verify-painter.lua").read_text(), "JOIN_PAINTER_ACCEPTANCE PASS")
            sample_outlet(photo, cameras["outlet"], native, output)
            station = survey["native_probes"]["right_exposed_crescent"]
            eye = [*station["xy_m"], station["ground_z_m"] + 1.65]
            bank_view = previous.pose(eye, (-297.5, 815.6, 142.9), 76)
            photo.setpose(bank_view, True)
            time.sleep(3)
            bank_frame = v.take_image(photo, output, "from-the-gravel-shelf", bank_view)
            b.write(output / "gravel-shelf-camera.json", dict(camera=bank_view, frame=bank_frame,
                    ground_clearance_m=1.65, release=identity))
            # Two captures from the same position in the build distinguish
            # a visible water surface from gravel that merely looks wet.
            water_trial = river.ROOT / "levels/warfare/pwr/terrain/trial_river_edge.lua"
            probe("surface-control-ready", water_trial.read_text(), "PWR_EDGE_READY PASS")
            try:
                for label, mode in (("surface-on", "control"), ("surface-off", "hide")):
                    probe(label, "PWREdgeStudy.apply('" + mode + "')", "PWR_EDGE_STUDY " + mode + " PASS")
                    photo.setpose(cameras["outlet"], True)
                    time.sleep(2.8)
                    v.take_image(photo, output, label, cameras["outlet"])
            finally:
                probe("surface-control-restored", "PWREdgeStudy.restore()", "PWR_EDGE_RESTORED PASS")
            optics = WORK / "water-optics" / "detail-wave.lua"
            if identity["archive"].endswith((".37.mjolnir", ".38.mjolnir", ".39.mjolnir")):
                verify_wave = """
                local count=0
                for _,r in ipairs(FindAllOf('BP_FluxSurface_River_C') or {}) do
                    if r:IsValid() and r:GetFullName():find('PersistentLevel',1,true) then
                        for i=1,#r.MaterialInstances do
                            local m=r.MaterialInstances[i]
                            if m:GetFullName():find('MID_MI_RiverSurfaceOver',1,true) then
                                local h=m:K2_GetScalarParameterValue(FName('DetailWaveHeight'))
                                print('LAKE_DETAIL_HEIGHT '..tostring(h))
                                assert(math.abs(h-3)<.0001)
                                count=count+1
                            end
                        end
                    end
                end
                assert(count>0)
                print('PWR_WAVE_RELEASE PASS')
                """
                probe("detail-wave-shipped", verify_wave, "PWR_WAVE_RELEASE PASS")
            elif optics.is_file():
                try:
                    probe("detail-wave-study", optics.read_text(), "PWR_WAVE_STUDY PASS")
                    time.sleep(3)
                    v.take_image(photo, output, "detail-wave-trial", cameras["outlet"])
                finally:
                    probe("detail-wave-restored", "if PWRWaveStudy then PWRWaveStudy.restore() end", "PWR_WAVE_RESTORE PASS")
            if contact_finish:
                verge_probe = candidate_work / "shore-contact/native/shore-foliage-readback.lua"
                probe("shore-planting", verge_probe.read_text(), "PWR_SHORE_FOLIAGE PASS")
            if candidate_work != WORK:
                try:
                    from water_motion import record
                    record(photo, b, cameras["riffle"], output)
                except (OSError, RuntimeError, ValueError) as err:
                    (output / "motion-capture.log").write_text(str(err), encoding="utf8")
    finally:
        b.run_lua(photo, photo.RESTORE)
    b.write(output / "photos.json", dict(release=identity, settings=settings, views=cameras, frames=frames))
    b.write(folder / "benchmark.json", dict(completed=True, release=identity, settings=settings, frames=frames))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument("label")
    parser.add_argument("--edge-trial", action="store_true")
    parser.add_argument("--performance-control", action="store_true")
    args = parser.parse_args()
    with previous.preferences(previous.BENCH / args.label), patch.object(b, "measure", run):
        b.run_release(args.release, args.label)
