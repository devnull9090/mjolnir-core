"""Read cooked/retargeted Landscape component LOD policy; never modify a package.

props_dump decodes with the explicit stock or Meteorite reflection schema.
Use the extracted final map world as --world for the final published check.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from landscape_lod_policy import validate_policy, digest

ROOT = Path(__file__).resolve().parents[2]


def parse_dump(text):
    rows = []; current = None
    for line in text.splitlines():
        if line.startswith('export '):
            current = None
            match = re.match(r'^export (\d+) (\S+) \(native tail', line)
            if match and match[2].rsplit('.',1)[-1] == 'LandscapeComponent':
                current = {'export':int(match[1]), 'SectionBaseX':0, 'SectionBaseY':0, 'ForcedLOD':-1}
                rows.append(current)
        elif current is not None:
            match = re.match(r'^\s+(SectionBaseX|SectionBaseY|ForcedLOD) = (-?\d+)(?:\s.*)?$', line)
            if match: current[match[1]] = int(match[2])
    return rows


def verify_rows(rows, policy):
    count = policy['grid']['components']
    step = policy['grid']['sections'] * policy['grid']['quads']
    forced = {tuple(row) for row in policy['forced_section_bases']}
    expected = {(i*step,j*step) for i in range(count) for j in range(count)}
    seen = set()
    for row in rows:
        key = (row['SectionBaseX'],row['SectionBaseY'])
        if key not in expected or key in seen:
            raise ValueError('Unexpected/duplicate cooked Landscape component '+repr(key))
        seen.add(key)
        want = 0 if key in forced else -1
        if row['ForcedLOD'] != want:
            raise ValueError(f'Cooked component {key} ForcedLOD={row["ForcedLOD"]}; expected {want}')
    if seen != expected: raise ValueError('Incomplete cooked Landscape component inventory')
    return {'components':len(seen),'forced_lod0':len(forced),'automatic':len(seen-forced)}


def runtime_script(policy):
    """Only reflected read APIs already exercised by the map loader; no setters."""
    keys = ','.join('["%d,%d"]=true'%tuple(row) for row in policy['forced_section_bases'])
    count = policy['grid']['components']
    step = policy['grid']['sections']*policy['grid']['quads']
    return f'''-- Read-only installed PWR Landscape LOD verification. No setters or input.
local forced={{{keys}}}
local seen,total,pinned={{}},0,0
for _,land in ipairs(FindAllOf("Landscape") or {{}}) do
    if land:IsValid() and land:GetFullName():find("/Game/Levels/Halo1/Solo/PWR/PWR",1,true) then
        local components=land.LandscapeComponents
        for i=1,#components do
            local c=components[i]
            assert(c and c:IsValid(),"Invalid PWR Landscape component")
            local x,y,lod=c.SectionBaseX,c.SectionBaseY,c.ForcedLOD
            local key=string.format("%d,%d",x,y)
            assert(x>=0 and y>=0 and x<{count*step} and y<{count*step} and x%{step}==0 and y%{step}==0,"Unexpected section base")
            assert(not seen[key],"Duplicate PWR Landscape section")
            seen[key]=true;total=total+1
            local expected=forced[key] and 0 or -1
            assert(lod==expected,"ForcedLOD mismatch at "..key..": "..tostring(lod))
            if forced[key] then pinned=pinned+1 end
            print(string.format("PWR_LANDSCAPE_LOD %d %d %d",x,y,lod))
        end
    end
end
assert(total=={count*count} and pinned=={len(policy['forced_section_bases'])},"Incomplete PWR Landscape LOD inventory")
print(string.format("PWR_LANDSCAPE_LOD PASS components=%d pinned=%d automatic=%d",total,pinned,total-pinned))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy',type=Path,required=True)
    parser.add_argument('--land',type=Path,required=True)
    parser.add_argument('--world',type=Path)
    parser.add_argument('--stock-world',type=Path)
    parser.add_argument('--global-paks',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--props-dump',type=Path,default=ROOT/'target/release/examples/props_dump.exe')
    args=parser.parse_args();policy=json.loads(args.policy.read_text())
    spec=json.loads((args.land/'landscape.json').read_text())
    validate_policy(policy,spec,args.land)
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'runtime-readback.lua').write_text(runtime_script(policy))
    if not args.world and not args.stock_world:
        print('Prepared read-only runtime helper; no cooked/runtime acceptance claimed')
        return
    if not args.global_paks:raise ValueError('--global-paks is required for explicit package decoding')
    reports=[]
    for kind,path,schema in [('stock',args.stock_world,'UE-5.5-stock.usmap'),('game',args.world,'Meteorite-2607-CU3.usmap')]:
        if path is None:continue
        result=subprocess.run([str(args.props_dump),str(args.global_paks),str(ROOT/'defs/ue'/schema),str(path)],capture_output=True,text=True,check=True)
        dump=args.out/(kind+'.properties.txt');dump.write_text(result.stdout)
        inventory=verify_rows(parse_dump(result.stdout),policy)
        reports.append({'encoding':kind,'package':str(path.resolve()),'package_sha256':digest(path),
                        'schema_sha256':digest(ROOT/'defs/ue'/schema),'dump_sha256':digest(dump),**inventory})
    report={'schema':'pwr-cooked-landscape-lod-check-v1','policy_sha256':digest(args.policy),
            'packages':reports,'runtime_check':'Prepared read-only helper; not executed by this tool'}
    (args.out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
