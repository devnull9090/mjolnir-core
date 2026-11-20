"""Keep the reversible Steam switch and the game bridge single-owner during QA."""
from pathlib import Path
import json,subprocess,sys,time
qa=Path(__file__).resolve().parent
sys.path.insert(0,str(qa.parents[1]/'landscape-distance/campaign-study'))
from compare_release import provision
def process_status():
    # The real status RPC includes a ping, which would race with a photographer
    # or driver on the native game's single request mailbox. This passive liveness
    # query enables identical process ownership/restore checks without issuing it.
    cmd="@(Get-CimInstance Win32_Process -Filter \"Name='HaloCampaignEvolved.exe'\" | Select-Object ProcessId,ExecutablePath) | ConvertTo-Json -Compress"
    for attempt in range(8):
        raw=subprocess.check_output(['powershell','-NoProfile','-Command',cmd],encoding='utf8').strip()
        data=json.loads(raw) if raw else []
        rows=data if isinstance(data,list) else [data]
        if not rows:return 'process      stopped'
        assert len(rows)==1,'Unexpected concurrent Halo sessions'
        executable=rows[0].get('ExecutablePath')
        if executable:
            assert Path(executable).resolve().is_relative_to(provision.GAME.resolve()),'Different Halo install active'
            return 'process      running, pid '+str(rows[0]['ProcessId'])
        # A PID can outlive its readable image path briefly during normal game_quit.
        # Wait for a fresh process snapshot before permitting any installation switch.
        time.sleep(.2)
    raise RuntimeError('Halo process exists but its executable owner could not be verified')
if __name__=='__main__':
    provision.status=process_status
    provision.supervise(Path(sys.argv[1]).resolve())
