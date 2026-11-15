// Explicit sole-player native Warthog tunnel acceptance. Never hosts/installs,
// creates vehicles, changes teams, or acts on any remote player.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { parseObjects, parsePlayers, parseSnapshot, guardSnapshot, guardOccupant, guardVehicleVacant, insideVolume }
  from '../../../../native/lobby/smoke-warfare-vehicles.mjs';
import { guardPlan } from '../../../../native/lobby/smoke-warfare-terrain.mjs';

const check=(ok,message)=>{if(!ok)throw new Error(message);};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const sha=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const metres=p=>p.map(x=>x*3.048);
const distance=(a,b)=>Math.hypot(...a.map((x,i)=>x-b[i]));
const repo=fileURLToPath(new URL('../../../../',import.meta.url));
const tag='objects\\vehicles\\human\\warthog\\warthog';

export function measureRoute(route,before,after,maximumStep=route.max_step_m) {
  check(route.direction?.[0]===0 && route.direction[1]===1,'Unexpected tunnel direction');
  const lateral=Math.abs(after[0]-route.start_m[0]);
  const progress=after[1]-route.start_m[1];
  const step=distance(before,after);
  const length=route.end_m[1]-route.start_m[1];
  const floorOffset=after[2]-route.floor_m;
  check(lateral<=route.max_lateral_m && progress>=-2 && progress<=length+12,
        'Vehicle left the measured tunnel corridor');
  check(Number.isFinite(maximumStep)&&maximumStep>0&&maximumStep<=40&&step<=maximumStep && floorOffset>=-.6 && floorOffset<=3,
        'Vehicle exceeded the measured support/movement envelope');
  return {lateral_m:lateral,progress_m:progress,step_m:step,floor_offset_m:floorOffset,length_m:length};
}

export async function main(argv=process.argv.slice(2)) {
  const options=new Set(argv),opt=(name,fallback)=>argv.find(v=>v.startsWith(name+'='))?.slice(name.length+1)??fallback;
  check(options.has('--drive'),'Explicit --drive is required; no game calls made');
  check(argv.every(v=>['--drive','--screenshots'].includes(v)||/^--(?:plan|out|base)=/.test(v)),'Unknown option');
  const selected=opt('--base','all');check(['all','red','blue','green'].includes(selected),'Invalid base');
  const planPath=path.resolve(opt('--plan',path.join(repo,'out/pwr/base-runtime/base-probe-plan.json')));
  const plan=JSON.parse(fs.readFileSync(planPath,'utf8')),planHash=sha(planPath);
  execFileSync('uv',['run','--python','3.12','python',path.join(repo,'levels/warfare/pwr/bases_v1/prepare_base_probe.py'),'verify',planPath],
    {cwd:repo,encoding:'utf8',windowsHide:true,timeout:30000});
  const routes=plan.vehicle_routes.filter(r=>selected==='all'||r.team===selected);
  const out=path.resolve(opt('--out',path.join(repo,`out/pwr/base-runtime/qa/base-drive-${Date.now()}.jsonl`)));
  fs.mkdirSync(path.dirname(out),{recursive:true});
  const record=data=>fs.appendFileSync(out,JSON.stringify({at:new Date().toISOString(),...data})+'\n');
  const {callTool}=await import('../../../../tools/mcp/game/game.mjs');
  const text=r=>(r.content??[]).filter(c=>c.type==='text').map(c=>c.text).join('\n');
  const call=async(name,args)=>{const r=await callTool(name,args);check(!r.isError,`${name}: ${text(r)}`);return text(r);};
  const status=await call('game_status',{}),pid=status.match(/^process\s+running, pid (\d+)$/m)?.[1];
  const install=status.match(/^install\s+(.+)$/m)?.[1]?.trim();check(pid&&install,'Game must already run in private PWR warfare');
  const bin=['Win64','WinGDK'].find(b=>fs.existsSync(path.join(install,'Meteorite','Binaries',b,'HaloCampaignEvolved.exe')));
  check(bin,'Unknown game binaries');
  const ue4ss=path.join(install,'Meteorite','Binaries',bin,'ue4ss'),native=path.join(ue4ss,'Mods','MJOLNIRLobby','native');
  const level=JSON.parse(fs.readFileSync(path.join(ue4ss,'MJOLNIRMaps','PWR','level.json'),'utf8'));
  guardPlan(plan,level,planHash);
  const lua=value=>{check(!value.includes(']==]'),'Invalid Lua literal');return `[==[${value.replaceAll('\\','/')}]==]`;};
  const dll=lua(path.join(native,'mjolnir_lobby.dll')),state=lua(path.join(native,'warfare_state.txt'));
  const read=`local f,e=package.loadlib(${dll},'mjolnir_warfare_pump'); assert(f,e); f(); local s=assert(io.open(${state},'rb')); print(s:read('a')); s:close()`;
  const cli=path.join(repo,'target/release/mjolnir.exe');
  let previous,unit,instance,vehicleHandle,inputStarted=false;
  const snapshot=async()=>{
    const s=parseSnapshot(await call('game_lua',{code:read,timeout_ms:5000})),p=guardSnapshot(s,previous);
    if(unit!==undefined)check(p.unit===unit&&s.instance===instance,'Player respawned or match changed');
    previous=s;record({event:'native_snapshot',...s});return s;
  };
  const inventory=s=>{
    const begin=Date.now();
    const live=name=>execFileSync(cli,['live','--pid',pid,name],{encoding:'utf8',windowsHide:true,timeout:15000});
    const players=parsePlayers(live('players')),objects=parseObjects(live('objects'));
    check(Date.now()-begin<2500,'Live inventory too old to authorize movement');
    record({event:'inventory',tick:s.tick,players,objects:objects.filter(o=>['vehicle','biped'].includes(o.kind))});
    return {players,objects};
  };
  const privateState=async()=>{
    const file=path.join(native,'auto_state.txt');
    const stamp=()=>{try{return fs.statSync(file,{bigint:true}).mtimeNs;}catch{return 0n;}};
    const before=stamp(),started=Date.now();await call('game_console',{command:'mjolnir_auto state'});
    while(Date.now()-started<5000){
      if(stamp()!==before){
        const f=Object.fromEntries(fs.readFileSync(file,'utf8').trim().split(/\r?\n/).map(s=>{const n=s.indexOf('=');return[s.slice(0,n),s.slice(n+1)];}));
        if(f.at&&f.public!==undefined){check(f.signed_in==='1'&&f.frontend==='0'&&f.public==='0'&&f.players==='1'
          &&Math.abs(Date.now()/1000-Number(f.at))<3,'Requires fresh private sole-player host');record({event:'private_guard',fields:f});return;}
      }
      await sleep(100);
    }
    throw new Error('No fresh private-state acknowledgement');
  };
  const hs=async line=>{
    check(line.length<255,'HaloScript exceeds native command limit');
    const script=lua(path.join(native,'script.txt')),body=lua(`${Date.now()}\n${line}\n`);
    await call('game_lua',{code:`local f=assert(io.open(${script},'wb')); f:write(${body}); f:close(); local r,e=package.loadlib(${dll},'mjolnir_sim_script'); assert(r,e); r()`});
    record({event:'hs_requested',line});await sleep(350);
  };
  const occupant=(s,inv)=>{
    const player=guardOccupant(s,inv.players,inv.objects,vehicleHandle),vehicle=inv.objects.find(o=>o.handle===vehicleHandle);
    check(vehicle?.tag===tag&&vehicle.healthPercent>0,'Warthog disappeared, changed type or died');return {player,vehicle};
  };
  const picture=async label=>{
    if(!options.has('--screenshots'))return;
    const r=await callTool('game_screenshot',{foreground:true,max_width:1280});
    const frame=r.content?.find(c=>c.type==='image'&&c.mimeType==='image/png'&&c.data);check(!r.isError&&frame,'Screenshot failed');
    const file=out.replace(/\.[^./\\]+$/,'')+'-'+label+'.png';fs.writeFileSync(file,Buffer.from(frame.data,'base64'));record({event:'screenshot',file});
  };
  const settleVehicle=async(label,baseline,route=null,brake=false)=>{
    inputStarted=true;
    await call('game_input',{method:'sendinput',gap_ms:0,steps:[{key:'w',up:true},{key:'s',up:true}]});
    const started=Date.now();let last,stable=0;
    while(Date.now()-started<18000){
      await sleep(300);await privateState();const s=await snapshot(),current=occupant(s,inventory(s));
      const position=metres(current.vehicle.position);
      check(current.player.healthPercent>=baseline.player.healthPercent-5&&current.vehicle.healthPercent>=baseline.vehicle.healthPercent-5,'Damage while stopping Warthog');
      if(route)measureRoute(route,last?.position??position,position,40);
      if(last){
        const dt=(s.tick-last.tick)/s.rate,speed=distance(position,last.position)/dt;
        check(dt>0&&dt<=6,'Stale native stopping sample');
        const forwardSpeed=(position[1]-last.position[1])/dt;
        stable=speed<.15?stable+1:0;
        record({event:'vehicle_settle',label,position,speed_mps:speed,forward_speed_mps:forwardSpeed,stable_samples:stable});
        if(stable>=3)return {s,current,position};
        // Short opposing-throttle pulses are issued only while actual native
        // movement is still forward. Stop pulsing as soon as it slows/reverses.
        if(brake&&forwardSpeed>.5){
          const response=await call('game_input',{method:'sendinput',gap_ms:0,steps:[{key:'s',hold:150}]});
          check(!/warning:|did not take focus/i.test(response),'Braking input lost focus');
        }
      }
      last={tick:s.tick,position};
    }
    throw new Error(`Warthog did not become stationary at ${label}; refusing further teleport/drive`);
  };
  try {
    record({event:'start',planPath,planHash,routes:routes.map(r=>r.team),pid,install});
    await privateState();await snapshot();await sleep(500);
    let s=await snapshot(),inv=inventory(s),initial=guardOccupant(s,inv.players,inv.objects);
    unit=initial.handle;instance=s.instance;
    const local=guardSnapshot(s),rank=s.ordinals[local.index],team=local.team===0?'red':'blue';
    const volumeName=`pwr_probe_hog_${team}`,volumes=level.blam.trigger_volumes.filter(v=>v.name===volumeName);
    check(volumes.length===1,'Missing installed Warthog fleet volume');
    const candidates=inv.objects.filter(o=>o.kind==='vehicle'&&o.parent===null&&insideVolume(o.position,volumes[0]));
    check(candidates.length===1&&candidates[0].tag===tag&&candidates[0].healthPercent>0,'Expected one healthy Warthog at its native spawn');
    guardVehicleVacant(candidates[0],inv.objects);vehicleHandle=candidates[0].handle;
    const list=`(volume_return_objects_by_type ${volumeName} 2)`;
    await hs(`(if (= (list_count ${list}) 1) (unit_enter_vehicle_immediate (player_get ${rank}) (vehicle (list_get ${list} 0)) "warthog_d"))`);
    s=await snapshot();inv=inventory(s);const baseline=occupant(s,inv);
    await settleVehicle('native-spawn',baseline);
    for(const route of routes){
      await privateState();s=await snapshot();occupant(s,inventory(s));
      await hs(`(object_teleport (unit_get_vehicle (player_get ${rank})) ${route.start_flag})`);
      const landing=await settleVehicle(route.team+'-entrance',baseline,route);
      s=landing.s;let current=landing.current,position=landing.position;
      check(distance(position.slice(0,2),route.start_m.slice(0,2))<2,'Warthog did not reach entrance flag');
      check(Math.sin(current.vehicle.yaw*Math.PI/180)>Math.cos(3*Math.PI/180),'Heading-control abort: Warthog is not aligned through tunnel');
      await picture(route.team+'-entrance');
      // The original plan's 20s authoring budget excludes bridge/inventory
      // latency. Keep its geometric envelope, with a bounded 90s live budget.
      const started=Date.now();let previousPosition=position,previousTick=s.tick,visitedHall=false,result,lastProgress=0,lastProgressAt=Date.now();
      for(let pulse=0;Date.now()-started<90000;pulse++){
        await privateState();s=await snapshot();current=occupant(s,inventory(s));
        check(current.player.healthPercent>=baseline.player.healthPercent-5&&current.vehicle.healthPercent>=baseline.vehicle.healthPercent-5,'Warthog/player took material damage');
        record({event:'drive_heading',team:route.team,vehicle_yaw:current.vehicle.yaw,player_body_yaw:current.player.yaw,
                camera_aim:'not exposed by native object inventory'});
        check(Math.sin(current.vehicle.yaw*Math.PI/180)>Math.cos(8*Math.PI/180),
              'Heading-control abort: native steering left the tunnel axis; this is not a collision-blockage result');
        inputStarted=true;
        const response=await call('game_input',{method:'sendinput',gap_ms:0,steps:[{key:'w',hold:pulse===0?250:500}]});
        check(!/warning:|did not take focus/i.test(response),'Drive input did not acquire game focus');
        s=await snapshot();current=occupant(s,inventory(s));position=metres(current.vehicle.position);
        const simulationSeconds=(s.tick-previousTick)/s.rate;
        check(simulationSeconds>0&&simulationSeconds<=6,'Stale native samples cannot certify a tunnel traversal');
        // A conservative speed bound scales with actual native time, so an
        // extra bridge round-trip is not mistaken for a physical teleport.
        const maximumStep=Math.min(40,35*simulationSeconds+2);
        result=measureRoute(route,previousPosition,position,maximumStep);
        check(position[1]>=previousPosition[1]-.15,'Warthog moved opposite the entrance heading');
        if(result.progress_m>lastProgress+.25){lastProgress=result.progress_m;lastProgressAt=Date.now();}
        check(Date.now()-lastProgressAt<10000,'Warthog made no meaningful forward progress for ten seconds');
        visitedHall ||= previousPosition[1]<=route.hall_m[1]&&position[1]>=route.hall_m[1];
        record({event:'drive_step',team:route.team,pulse,position,...result,simulation_seconds:simulationSeconds,
                maximum_step_m:maximumStep,visited_hall:visitedHall});
        previousPosition=position;previousTick=s.tick;
        if(result.progress_m>=result.length_m-2)break;
      }
      check(visitedHall&&result&&result.progress_m>=result.length_m-2,'Warthog did not traverse entrance, main hall and rear court');
      check(current.player.healthPercent>=baseline.player.healthPercent-5&&current.vehicle.healthPercent>=baseline.vehicle.healthPercent-5,'Traversal damaged Warthog/player');
      const stopped=await settleVehicle(route.team+'-exit',baseline,route,true);
      position=stopped.position;
      await picture(route.team+'-exit');
      record({event:'route_complete',team:route.team,success:true,position,...result});
      console.log(`${route.team}: Warthog traversed ${result.progress_m.toFixed(2)}m through the base`);
    }
    record({event:'complete',success:true,completed_bases:routes.map(r=>r.team),note:'Player remains seated in the existing Warthog; private match continues.'});
    console.log(JSON.stringify({out,success:true,bases:routes.map(r=>r.team)}));
  } catch(error){record({event:'aborted',error:String(error)});throw error;}
  finally {if(inputStarted)try{await call('game_input',{method:'sendinput',gap_ms:0,steps:[{key:'w',up:true},{key:'s',up:true}]});}
    catch(error){record({event:'release_failed',error:String(error)});}}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  main().catch(error=>{console.error(String(error));process.exitCode=1;});
}
