import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {sampleFleet,retentionComplete,main} from './observe-warfare-vehicles.mjs';
const policy = JSON.parse(fs.readFileSync(new URL('../../levels/warfare/pwr/vehicle-spawn-policy-v1.json',import.meta.url),'utf8'));
const objects = () => policy.vehicles.map((r,i) => ({handle:0xe2000010+i,kind:'vehicle',parent:null,player:'',healthPercent:100,
  tag:r.type==='scorpion'?'objects\\vehicles\\human\\scorpion\\scorpion':'objects\\vehicles\\covenant\\banshee\\banshee',
  position:[r.new_pos_cm[0]/304.8,-r.new_pos_cm[1]/304.8,(r.new_pos_cm[2]/100-.3)/3.048]}));
test('observer requires explicit opt-in before any bridge import',async()=>{
  await assert.rejects(main([]),/No game calls made/);
  await assert.rejects(main(['--observe','--seconds=30']),/Explicit --seal/);
});
test('all eight healthy stationary salted handles survive a normal sample',()=>{
  const first=sampleFleet(policy,objects(),[0,0,110]);
  assert.equal(first.length,8);
  assert.deepEqual(sampleFleet(policy,objects(),[0,0,110],first),first);
});
test('missing or silently replaced vehicles cannot pass retention',()=>{
  const first=sampleFleet(policy,objects(),[0,0,110]);
  assert.throws(()=>sampleFleet(policy,objects().slice(1),[0,0,110],first),/Missing/);
  const changed=objects();changed[0].handle+=65536;
  assert.throws(()=>sampleFleet(policy,changed,[0,0,110],first),/handle replaced/);
});
test('proximity, health loss, movement and occupied vehicle reject',()=>{
  const first=sampleFleet(policy,objects(),[0,0,110]);
  assert.throws(()=>sampleFleet(policy,objects(),first[0].position_m),/proximity/);
  let changed=objects();changed[0].healthPercent=99;
  assert.throws(()=>sampleFleet(policy,changed,[0,0,110]),/health/);
  changed=objects();changed[0].position[2]-=1;
  assert.throws(()=>sampleFleet(policy,changed,[0,0,110]),/threshold/);
  changed=objects();changed.push({handle:555,kind:'biped',parent:changed[0].handle,player:''});
  assert.throws(()=>sampleFleet(policy,changed,[0,0,110]),/occupied/);
  changed=objects();changed[0].position[0]+=.2;
  assert.throws(()=>sampleFleet(policy,changed,[0,0,110],first),/moved/);
});
test('clock requires 180 real and simulation seconds, same match and rate',()=>{
  const first={at_ms:1000,tick:100,rate:30,instance:'777'};
  const end={...first,at_ms:181000,tick:5500};
  assert.equal(retentionComplete(first,end).complete,true);
  assert.equal(retentionComplete(first,{...end,at_ms:180999}).complete,false);
  assert.equal(retentionComplete(first,{...end,tick:5499}).complete,false);
  assert.throws(()=>retentionComplete(first,end,30),/at least 180/);
  assert.throws(()=>retentionComplete(first,{...end,instance:'778'}),/instance/);
});
