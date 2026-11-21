#!/usr/bin/env node
// Opt-in private QA: damage one verified unoccupied Scorpion body, or observe
// a vehicle after an independently recorded drive/detach. No object deletion,
// creation or teleportation. The abandonment mode is entirely read-only.
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {verifySeal} from './observe-warfare-vehicles.mjs';
import {parseSnapshot,guardSnapshot,parseObjects,parsePlayers,guardOccupant,guardVehicleVacant,insideVolume}
  from './smoke-warfare-vehicles.mjs';
const check=(ok,message)=>{if(!ok)throw Error(message);};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const distance=(a,b)=>Math.hypot(...a.map((x,i)=>x-b[i]));
const TAG='objects\\vehicles\\human\\scorpion\\scorpion';
// CU4 0x352250 matches model+0x9c material names, not damage-section names.
// The shipped Scorpion's hull_back material maps to body section 0; "body"
// is absent from that material table and silently produces no damage.
export const SCORPION_BODY_MATERIAL='hull_back';

export function bodyDepleted(exact, handle) {
  check(exact?.schema==='mjolnir-object-health-v1'&&exact.handle===handle&&exact.kind==='vehicle'
    &&exact.body_section_present===true&&Number.isFinite(exact.maximum_body)&&exact.maximum_body>0
    &&Number.isFinite(exact.body_fraction)&&Number.isInteger(exact.body_fraction_bits)
    &&exact.body_fraction_bits>=0&&exact.body_fraction_bits<=0xffffffff,'Invalid exact native body-health evidence');
  const bits=new DataView(new ArrayBuffer(4));bits.setUint32(0,exact.body_fraction_bits,true);
  const fraction=bits.getFloat32(0,true);
  check(Number.isFinite(fraction)&&Math.fround(exact.body_fraction)===fraction,'Exact health number and float32 bits disagree');
  return fraction<=0;
}

export function guardDestructionTarget(snapshot,players,objects,volume) {
  const local=guardSnapshot(snapshot), body=guardOccupant(snapshot,players,objects);
  check(body.healthPercent===100,'Local player must be healthy and unseated');
  const candidates=objects.filter(o=>o.kind==='vehicle' && o.parent===null && insideVolume(o.position,volume));
  check(candidates.length===1 && candidates[0].tag===TAG && candidates[0].healthPercent===100,
    'Exactly one healthy stock root Scorpion must occupy the installed volume');
  const target=candidates[0];guardVehicleVacant(target,objects);
  const position=target.position.map(v=>v*3.048);
  check(distance(local.position,position)>=60,'Player must remain at least 60m from the destruction target');
  check(objects.filter(o=>o.kind==='vehicle' && o.parent===null && o.handle!==target.handle)
    .every(o=>distance(o.position.map(v=>v*3.048),position)>=15),
    'Another root vehicle is within the 15m blast-clearance guard');
  return target;
}

export function damageCommand(team) {
  check(['red','blue'].includes(team),'Team must be red or blue');
  const objects=`(volume_return_objects_by_type pwr_probe_tank_${team} 2)`;
  const line=`(if (= (list_count ${objects}) 1) (damage_object (list_get ${objects} 0) "${SCORPION_BODY_MATERIAL}" 1000))`;
  check(line.length<255,'HaloScript command exceeds bounded request length');
  return line;
}

export async function main(argv=process.argv.slice(2)) {
  const abandoning=argv.includes('--observe-abandonment');
  check(argv.includes('--destroy')!==abandoning,'No game calls made. Choose explicit --destroy or --observe-abandonment.');
  check(argv.every(v=>['--destroy','--observe-abandonment'].includes(v)||/^--(?:seal|out|team|drive-receipt|placement)=/.test(v)),'Unknown option');
  const option=n=>argv.find(v=>v.startsWith(`--${n}=`))?.slice(n.length+3);
  const sealPath=option('seal'),out=option('out'),team=option('team')??'blue';
  const line=abandoning?null:damageCommand(team);
  check(sealPath&&out&&!fs.existsSync(out),'Explicit --seal and new --out required');
  const {seal,policy,level}=verifySeal(sealPath);
  check(seal.exact_health_cli&&seal.critical.some(row=>path.resolve(row.path)===path.resolve(seal.exact_health_cli)),
    'Destruction evidence requires the sealed exact-health QA CLI');
  const placementName=abandoning?option('placement'):`pwr_tank_${team}_0`;
  check(/^pwr_(tank|banshee)_(red|blue)_0$/.test(placementName??''),'Expected a sealed first Tank/Banshee placement');
  const placement=policy.vehicles.find(v=>v.name===placementName);
  const volumes=level.blam.trigger_volumes.filter(v=>v.name===placementName.replace(/^pwr_/,'pwr_probe_').replace(/_0$/,''));
  check(placement&&volumes.length===1,'Missing sealed tank placement or installed probe');
  const targetTag=placement.type==='scorpion'?TAG:'objects\\vehicles\\covenant\\banshee\\banshee';
  let cleanup;
  if(abandoning) {
    check(option('drive-receipt'),'Abandonment observation requires a fresh guarded drive/detach receipt');
    cleanup=JSON.parse(fs.readFileSync(option('drive-receipt'),'utf8'));
    check(cleanup.success===true&&cleanup.parent?.tag===targetTag&&cleanup.parent?.kind==='vehicle'
      &&cleanup.parent?.parent===null&&cleanup.finalBody?.parent===null,
      'Drive receipt does not identify a successfully detached matching root vehicle');
    check(Math.abs(Date.now()-Date.parse(cleanup.at))<30000,'Drive/detach receipt must be less than 30 seconds old');
  }
  const volume=volumes[0],native=path.join(path.dirname(path.dirname(path.dirname(seal.installed_level))),'Mods/MJOLNIRLobby/native');
  const lua=s=>`[==[${s.replaceAll('\\','/')}]==]`;
  const stateCode=`local f=assert(package.loadlib(${lua(path.join(native,'mjolnir_lobby.dll'))},'mjolnir_warfare_pump'));f();local s=assert(io.open(${lua(path.join(native,'warfare_state.txt'))},'rb'));print(s:read('a'));s:close()`;
  const {callTool}=await import('../../tools/mcp/game/game.mjs');
  const text=r=>(r.content??[]).filter(c=>c.type==='text').map(c=>c.text).join('\n');
  const call=async(name,args)=>{const r=await callTool(name,args);check(!r.isError,text(r));return text(r);};
  const status=await call('game_status',{}),pid=status.match(/^process\s+running, pid (\d+)$/m)?.[1];
  check(pid,'Game must already be running');
  const install=status.match(/^install\s+(.+)$/m)?.[1]?.trim();
  check(install&&path.resolve(native).startsWith(path.resolve(install)+path.sep),'Seal belongs to another install');
  const cli=fileURLToPath(new URL('../../target/release/mjolnir.exe',import.meta.url));
  const live=n=>execFileSync(cli,['live','--pid',pid,n],{encoding:'utf8',timeout:15000,windowsHide:true});
  const exactHealth=handle=>JSON.parse(execFileSync(seal.exact_health_cli,
    ['live','--pid',pid,'object-health','--handle','0x'+handle.toString(16)],
    {encoding:'utf8',timeout:15000,windowsHide:true}));
  fs.mkdirSync(path.dirname(path.resolve(out)),{recursive:true});
  const file=fs.openSync(out,'wx');
  const record=row=>fs.writeSync(file,JSON.stringify({at:new Date().toISOString(),...row})+'\n');
  let previous,unit;
  const sample=async()=>{
    const started=Date.now();
    const snapshot=parseSnapshot(await call('game_lua',{code:stateCode,timeout_ms:5000}));
    guardSnapshot(snapshot,previous);
    const players=parsePlayers(live('players')),objects=parseObjects(live('objects'));
    const body=guardOccupant(snapshot,players,objects);
    check(body.healthPercent===100&&(unit===undefined||body.handle===unit),'Player died or lost health during destruction probe');
    check(Date.now()-started<2500,'Native sample too slow');
    previous=snapshot;unit=body.handle;
    record({event:'sample',snapshot,players,objects:objects.filter(o=>o.kind==='vehicle'||o.kind==='biped')});
    return{snapshot,players,objects};
  };
  try {
    record({event:'start',pid,seal:sealPath,team,placement,mode:abandoning?'abandonment':'destruction',
      damage_mechanism:abandoning?'none; observation only':'native damage_object hull_back material1000; no deletion',line,cleanup});
    const auto=path.join(native,'auto_state.txt'),old=fs.existsSync(auto)?fs.statSync(auto).mtimeMs:0;
    await call('game_console',{command:'mjolnir_auto state'});
    const start=Date.now();
    while((!fs.existsSync(auto)||fs.statSync(auto).mtimeMs===old)&&Date.now()-start<5000)await sleep(50);
    check(fs.existsSync(auto)&&fs.statSync(auto).mtimeMs!==old,'No fresh private-session acknowledgement');
    const fields=Object.fromEntries(fs.readFileSync(auto,'utf8').trim().split(/\r?\n/).map(s=>{const i=s.indexOf('=');return[s.slice(0,i),s.slice(i+1)];}));
    check(fields.public==='0'&&fields.frontend==='0'&&fields.signed_in==='1'&&fields.players==='1'
      &&Math.abs(Date.now()/1000-Number(fields.at))<3,'Fresh private solo guard failed');
    record({event:'private_guard',fields});
    await sample();await sleep(350);
    const initial=await sample();
    let target;
    if(abandoning) {
      check(initial.snapshot.instance===cleanup.after.instance&&initial.snapshot.players[0].unit===cleanup.after.players[0].unit,
        'Drive/detach receipt belongs to a different player or match');
      target=initial.objects.find(o=>o.handle===cleanup.parent.handle);
      check(target?.tag===targetTag&&target.healthPercent===100,'Driven-away vehicle disappeared or was damaged before observation');
      guardVehicleVacant(target,initial.objects);
      const spawn=[placement.new_pos_cm[0]/100,-placement.new_pos_cm[1]/100,placement.new_pos_cm[2]/100];
      const at=target.position.map(n=>n*3.048);
      check(distance(at,spawn)>3,'Vehicle was not meaningfully driven from its spawn');
      check(distance(at,initial.snapshot.players[0].position)>=60,'Player remains too close to permit abandonment');
    } else target=guardDestructionTarget(initial.snapshot,initial.players,initial.objects,volume);
    record({event:'target_verified',target});
    const initialHealth=exactHealth(target.handle);bodyDepleted(initialHealth,target.handle);
    check(initialHealth.body_fraction>0,'Selected target is already depleted');
    record({event:'exact_health_before',target:target.handle,exact:initialHealth});
    const commandAt=Date.now();
    if(!abandoning) {
      const result=await call('game_lua',{code:`local s=assert(io.open(${lua(path.join(native,'script.txt'))},'wb'));s:write(${lua(commandAt+'\n'+line+'\n')});s:close();local f=assert(package.loadlib(${lua(path.join(native,'mjolnir_lobby.dll'))},'mjolnir_sim_script'));f()`});
      record({event:'damage_requested',line,result,target:target.handle});
    }
    let deathAt=null,lastPresent=commandAt,firstMissing=null,lastNoReplacement=commandAt;
    while(Date.now()-commandAt<(abandoning?120000:90000)) {
      await sleep(Date.now()-commandAt<5000?250:1000);
      const current=await sample(),oldObject=current.objects.find(o=>o.handle===target.handle);
      if(abandoning) {
        if(oldObject) {
          check(firstMissing===null&&oldObject.healthPercent===100,'Driven vehicle was damaged or reappeared; not a clean abandonment');
          guardVehicleVacant(oldObject,current.objects);
          check(distance(oldObject.position.map(n=>n*3.048),current.snapshot.players[0].position)>=60,
            'Player proximity could suppress genuine abandonment');
          lastPresent=Date.now();
        } else if(firstMissing===null) {
          firstMissing=Date.now();record({event:'healthy_vehicle_abandoned',target:target.handle,elapsed_seconds:(firstMissing-commandAt)/1000});
        }
      }
      if(!abandoning&&oldObject&&oldObject.healthPercent===0&&deathAt===null) {
        const exact=exactHealth(target.handle);
        record({event:'exact_health_check',target:target.handle,rounded_percent:oldObject.healthPercent,exact});
        if(bodyDepleted(exact,target.handle)) {
          deathAt=Date.now();record({event:'body_depleted',target:target.handle,exact,elapsed_seconds:(deathAt-commandAt)/1000});
        }
      }
      const replacements=current.objects.filter(o=>o.kind==='vehicle'&&o.parent===null&&o.tag===targetTag
        &&o.handle!==target.handle&&o.healthPercent===100&&insideVolume(o.position,volume));
      check(replacements.length<=1,'Multiple new tanks in the original probe volume');
      if(replacements.length===1) {
        check(abandoning?firstMissing!==null:deathAt!==null,
          'Replacement alone cannot prove the required observed abandonment or destruction');
        const replacement=replacements[0];guardVehicleVacant(replacement,current.objects);
        const elapsed=(Date.now()-(abandoning?firstMissing:deathAt))/1000,expected=Number(placement.unchanged_spawn_seconds);
        const timing=abandoning?{lower_seconds:(lastNoReplacement-firstMissing)/1000,upper_seconds:(Date.now()-lastPresent)/1000}:null;
        check(abandoning?timing.lower_seconds<=expected+3&&timing.upper_seconds>=expected-3:
          elapsed>=expected-3&&elapsed<=expected+10,'Observed replacement timing does not match the preserved spawn timer');
        const spawn=[placement.new_pos_cm[0]/100,-placement.new_pos_cm[1]/100,placement.new_pos_cm[2]/100];
        check(distance(replacement.position.map(n=>n*3.048),spawn)<1.3,'Replacement does not use the corrected spawn origin');
        verifySeal(sealPath);
        record({event:'complete',success:true,old_handle:target.handle,new_handle:replacement.handle,
          body_depletion_observed:deathAt!==null,healthy_abandonment_observed:abandoning&&firstMissing!==null,
          mode:abandoning?'abandonment':'destruction',respawn_seconds:elapsed,respawn_interval:timing,
          configured_spawn_seconds:expected,replacement});
        console.log(JSON.stringify({success:true,out,respawn_seconds:elapsed,old_handle:target.handle,new_handle:replacement.handle}));return;
      }
      lastNoReplacement=Date.now();
      if(!abandoning&&deathAt===null&&Date.now()-commandAt>5000)throw Error('Native body depletion was not observed; stop without repeated damage or deletion');
    }
    throw Error('No healthy native replacement appeared within the bounded observation period');
  } catch(error) {record({event:'aborted',error:String(error)});throw error;}
  finally {fs.closeSync(file);}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))
  main().catch(error=>{console.error(error.message);process.exitCode=1;});
