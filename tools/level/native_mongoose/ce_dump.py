"""Read the CE Mongoose straight from the map into ce.json: nodes, markers,
regions, collision nodes, mass points and the animation graph. Writes into MJ_NATIVE_WORK."""
import json, os, struct, sys
import numpy as np

SP = os.environ["MJ_NATIVE_WORK"]
sys.path.insert(0, SP)
sys.path.insert(0, SP + "/pose")
import ce_antr as A  # opens the map and joins the protected tag names
from cevehi import refl, f, dep

b, off, tags, P = A.b, A.off, A.tags, A.P
s = A.s


def find(cls, path):
    for e in tags.values():
        if e.get("cls") == cls and e.get("path", "").replace(chr(92), "/") == path:
            return e
    raise SystemExit(f"no {cls} {path}")


veh = None
for e in tags.values():
    if e.get("cls") == "vehi" and "1038" in str(e.get("path")):
        veh = e
cands = [(e["path"]) for e in tags.values() if e.get("cls") == "vehi"]
print(cands)
mod = find("mod2", "protected/mod2/1040")
antr = find("antr", "protected/antr/1051")
coll = find("coll", "protected/coll/1052")
phys = find("phys", "protected/phys/1053")

out = {}
out["nodes"] = [{k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in n.items()} for n in A.nodes(mod)]
out["markers"] = [{k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in n.items()} for n in A.markers(mod)]

# regions and permutations of the model
m = off(mod["data"])
c, a = refl(b, m + 0xC4)
regs = []
for i in range(c):
    q = off(a) + 76 * i
    pc, pa = refl(b, q + 0x40)
    regs.append({"name": s(q), "perms": [s(off(pa) + 88 * j) for j in range(pc)]})
out["model_regions"] = regs

# animation graph
Ad = off(antr["data"])
out["antr_nodes"] = []
c, a = refl(b, Ad + 0x68)
for i in range(c):
    q = off(a) + 64 * i
    sib, ch, par = struct.unpack_from("<hhh", b, q + 32)
    fl = struct.unpack_from("<I", b, q + 40)[0]
    out["antr_nodes"].append(dict(name=s(q), sib=sib, child=ch, parent=par, flags=fl, base=f(b, q + 44, 3), range=f(b, q + 56)))

anims = A.anims(Ad)
out["animations"] = []
for an in anims:
    o = an["o"]
    fi_type = struct.unpack_from("<H", b, o + 38)[0]
    loop = struct.unpack_from("<h", b, o + 46)[0]
    tf = struct.unpack_from("<II", b, o + 0x5C)
    rf = struct.unpack_from("<II", b, o + 0x6C)
    sf = struct.unpack_from("<II", b, o + 0x7C)
    frames = []
    for fr in range(max(an["frames"], 1)):
        d = A.decode(an, fr)
        frames.append([{"r": x[0].tolist(), "t": x[1].tolist(), "s": float(x[2])} for x in d])
    fis, _, _, fip = struct.unpack_from("<IIII", b, o + 72)
    finfo = b[off(fip):off(fip) + fis].hex() if fis and fip else ""
    out["animations"].append(dict(i=an["i"], name=an["name"], type=an["type"], frames=an["frames"], frame_info_type=fi_type,
                                  loop=loop, nodes=an["nodes"], flags=an["flags"], trans_flags=tf[0], rot_flags=rf[0], scale_flags=sf[0],
                                  frame_info=finfo, data=frames))

c, a = refl(b, Ad + 0x24)
veh_blocks = []
for i in range(c):
    q = off(a) + 116 * i
    v = dict(right_yaw=f(b, q), left_yaw=f(b, q + 4), right_n=struct.unpack_from("<h", b, q + 8)[0], left_n=struct.unpack_from("<h", b, q + 10)[0],
             down=f(b, q + 12), up=f(b, q + 16), down_n=struct.unpack_from("<h", b, q + 20)[0], up_n=struct.unpack_from("<h", b, q + 22)[0])
    ac, aa = refl(b, q + 92)
    v["slots"] = [struct.unpack_from("<h", b, off(aa) + 2 * k)[0] for k in range(ac)]
    sc, sa = refl(b, q + 104)
    v["suspension"] = []
    for k in range(sc):
        z = off(sa) + 20 * k
        mp, an = struct.unpack_from("<hh", b, z)
        v["suspension"].append(dict(mass_point=mp, animation=an, extension=f(b, z + 4), compression=f(b, z + 8)))
    veh_blocks.append(v)
out["vehicle_anims"] = veh_blocks

# units block, for the seat modes this graph holds
c, a = refl(b, Ad + 0x0C)
out["unit_blocks"] = c
c, a = refl(b, Ad + 0x00)
objs = []
for i in range(c):
    q = off(a) + 20 * i
    objs.append(struct.unpack_from("<hhh", b, q))
out["object_blocks"] = objs

# physics mass points
p = off(phys["data"])
out["phys"] = dict(radius=f(b, p), moment=f(b, p + 4), mass=f(b, p + 8), com=f(b, p + 0xC, 3), density=f(b, p + 0x18), gravity=f(b, p + 0x1C),
                   gfric=f(b, p + 0x20), gdepth=f(b, p + 0x24), gdamp=f(b, p + 0x28), k1=f(b, p + 0x2C), k0=f(b, p + 0x30))
pc, pa = refl(b, p + 0x68)
out["phys"]["powered"] = [dict(name=s(off(pa) + 128 * i)) for i in range(pc)]
mc, ma = refl(b, p + 0x74)
mps = []
for i in range(mc):
    q = off(ma) + 128 * i
    mps.append(dict(name=s(q), powered=struct.unpack_from("<h", b, q + 32)[0], model_node=struct.unpack_from("<h", b, q + 34)[0],
                    flags=struct.unpack_from("<I", b, q + 36)[0], rel_mass=f(b, q + 40), mass=f(b, q + 44), rel_density=f(b, q + 48), density=f(b, q + 52),
                    position=f(b, q + 56, 3), forward=f(b, q + 68, 3), up=f(b, q + 80, 3), friction_type=struct.unpack_from("<H", b, q + 92)[0],
                    radius=f(b, q + 112) if 0 else None, raw=b[q + 92:q + 128].hex()))
out["phys"]["mass_points"] = mps

# collision nodes
g = off(coll["data"])
out["coll_raw_ok"] = True
json.dump(out, open(os.path.join(SP, "nx/native/ce.json"), "w"), indent=1)
print("nodes", [n["name"] for n in out["nodes"]])
print("antr nodes", [(n["name"], n["parent"]) for n in out["antr_nodes"]])
for an in out["animations"]:
    print({k: v for k, v in an.items() if k not in ("data", "frame_info")})
print(json.dumps(out["vehicle_anims"], indent=0)[:1500])
print(json.dumps(out["phys"])[:3000])
print(sorted(set((m["name"], m["node"]) for m in out["markers"])))
print(out["model_regions"])
