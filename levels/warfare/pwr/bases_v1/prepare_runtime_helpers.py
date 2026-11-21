"""Merge only the previously tested PWR helper changes into the installed runtime.

This writes an isolated candidate and CPU-test fixture; it never installs files.
The merge base is the source commit used by the PWR worktree, while the current
side is the actual installed runtime, retaining newer upstream implementations.
"""
from pathlib import Path
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
GAME = Path('C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved')
MODS = GAME/'Meteorite/Binaries/Win64/ue4ss/Mods'
OUT = ROOT/'out/pwr/base-runtime/runtime-repair'
BASE = '45be63dedc3b07e6c2650b4d4906773905586e1e'
HELPERS = {
    'MJOLNIRHud/Scripts/chat.lua': 'Keep M as text while chat or rules have keyboard focus.',
    'MJOLNIRHud/Scripts/class_lifetime.lua': 'Permit the existing allowlisted TacticalMap widget class.',
    'MJOLNIRHud/Scripts/markers.lua': 'Connect native Warfare snapshots to capture markers and canopy presentation.',
    'MJOLNIRHud/Scripts/scoreboard.lua': 'Register descriptors and display authoritative native team scores.',
    'MJOLNIRLevelLoader/Scripts/variant_settings.lua': 'Apply Warfare fixed settings while preserving its compiled score threshold.',
    'MJOLNIRLobby/Scripts/gametype.lua': 'Use the descriptor-provided mode icon.',
    'MJOLNIRLobby/Scripts/class_lifetime.lua': 'Keep the shared UI class allowlist consistent with the tactical map integration.',
}
STANDALONE = [
    'MJOLNIRLevelLoader/Scripts/mode_descriptors.lua',
    'MJOLNIRLevelLoader/Scripts/warfare.lua',
    'MJOLNIRLevelLoader/Scripts/flux_runtime.lua',
    'MJOLNIRHud/Scripts/tactical_map.lua',
    'MJOLNIRHud/Scripts/warfare.lua',
    'MJOLNIRHud/Scripts/warfare_canopy.lua',
]

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def normalized(data):
    return data.decode('utf-8-sig').replace('\r\n', '\n').encode('utf-8')

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')

def main():
    rows, diffs = [], []
    with tempfile.TemporaryDirectory(prefix='pwr-helpers-') as tmp:
        tmp = Path(tmp)
        for relative, reason in HELPERS.items():
            installed, custom = MODS/relative, ROOT/'mods'/relative
            base = subprocess.check_output(['git','show',BASE+':mods/'+relative], cwd=ROOT)
            current_data, custom_data = normalized(installed.read_bytes()), normalized(custom.read_bytes())
            for name, data in [('current',current_data),('base',normalized(base)),('custom',custom_data)]:
                (tmp/name).write_bytes(data)
            result = subprocess.run(['git','merge-file','-p',str(tmp/'current'),str(tmp/'base'),str(tmp/'custom')], capture_output=True)
            merged = result.stdout
            if result.returncode and relative == 'MJOLNIRHud/Scripts/markers.lua':
                # Both branches append independent diagnostic fields at the
                # same location. Retain the new roster diagnostic and append
                # Warfare's snapshot diagnostic; never prefer either branch.
                conflict = re.compile(r'^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*\n', re.M | re.S)
                matches = list(conflict.finditer(merged.decode()))
                if len(matches) != 1 or matches[0][1] != ('        local r = roster and roster.read()\n'
                        '        parts[#parts + 1] = r and "from the simulation" or "from actors"\n') or 'if match.warfare then' not in matches[0][2]:
                    raise RuntimeError('Unreviewed marker merge conflict')
                merged = conflict.sub(lambda m: m[1]+m[2],merged.decode()).encode()
            elif result.returncode:
                raise RuntimeError('Helper merge conflicts: '+relative)
            target = OUT/'lua/Mods'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(merged)
            diff = list(difflib.unified_diff(current_data.decode().splitlines(True), merged.decode().splitlines(True), fromfile='installed/'+relative, tofile='candidate/'+relative))
            diffs.extend(diff)
            rows.append({'relative':relative,'installed':str(installed),'candidate':str(target),
                         'before_sha256':sha(installed),'candidate_sha256':sha(target),
                         'base_commit':BASE,'custom_source':str(custom),'custom_source_sha256':sha(custom),
                         'reason':reason,'added_lines':sum(x.startswith('+') and not x.startswith('+++') for x in diff),
                         'removed_lines':sum(x.startswith('-') and not x.startswith('---') for x in diff)})
    preserved=[]
    for relative in STANDALONE:
        installed, custom = MODS/relative, ROOT/'mods'/relative
        if normalized(installed.read_bytes()) != normalized(custom.read_bytes()):
            raise RuntimeError('Installed standalone PWR helper differs from proven source: '+relative)
        preserved.append({'relative':relative,'installed':str(installed),'sha256':sha(installed),
                          'custom_source':str(custom),'custom_source_sha256':sha(custom)})
    write(OUT/'lua/helpers.receipt.json', {'schema':'pwr-runtime-lua-helper-candidates-v1',
          'installed_modified':False,'files':rows,'preserved_helpers':preserved})
    (OUT/'lua/helpers.diff').write_text(''.join(diffs), encoding='utf-8')
    fixture = OUT/'test-root'
    for mod in ['MJOLNIRLobby','MJOLNIRLevelLoader','MJOLNIRHud']:
        shutil.copytree(MODS/mod/'Scripts',fixture/'mods'/mod/'Scripts',dirs_exist_ok=True)
    for source in (OUT/'lua/Mods').rglob('*.lua'):
        target=fixture/'mods'/source.relative_to(OUT/'lua/Mods')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source,target)
    print(json.dumps({'helpers':len(rows),'preserved_helpers':len(preserved),'fixture':str(fixture)}))

if __name__ == '__main__': main()
