import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {guardDestructionTarget,damageCommand,bodyDepleted,main,SCORPION_BODY_MATERIAL} from './smoke-warfare-vehicle-destruction.mjs';
const unit=0xe2000001,target=0xe2000002;
const snapshot={ready:1,status:2,host:1,layout:3,phase:2,globals:[2,0,20571,0,60,0,0,0,0,0,0,0],
  connected:1,instance:'77',rate:30,tick:100,sampled_ms:5000,
  players:[{index:7,unit,team:0,stage:5,localUser:0,position:[0,0,0]}],ordinals:{7:0}};
const players=[{index:7,unit,team:0}];
const tank={handle:target,kind:'vehicle',parent:null,player:'',healthPercent:100,
  tag:'objects\\vehicles\\human\\scorpion\\scorpion',position:[100/3.048,0,0]};
const body={handle:unit,kind:'biped',parent:null,player:'player 7',healthPercent:100,position:[0,0,0]};
const volume={pos:[9500,500,-300],forward:[1,0,0],up:[0,0,1],extents:[10/3.048,10/3.048,10/3.048]};
test('destruction requires explicit opt-in before bridge import',async()=>{
  await assert.rejects(main([]),/No game calls made/);
  await assert.rejects(main(['--destroy','--team=green']),/Team must/);
});
test('damage command targets a shipped collision material mapped to body, not the no-op section name',()=>{
  const shipped=JSON.parse(fs.readFileSync(new URL('./fixtures/scorpion-damage-material.json',import.meta.url),'utf8'));
  assert.equal(shipped.material_table_offset,shipped.native_material_lookup.count_offset);
  assert.equal(shipped.material_stride,shipped.native_material_lookup.entry_size);
  assert.equal(shipped.materials.some(m=>m.name==='body'),false);
  assert.deepEqual(shipped.materials.filter(m=>m.name===SCORPION_BODY_MATERIAL),[{name:'hull_back',damage_section:0}]);
  const line=damageCommand('blue');
  assert.ok(line.length<255);
  assert.match(line,/damage_object.*"hull_back" 1000/);
  assert.match(line,/if \(= \(list_count/);
  assert.doesNotMatch(line,/object_destroy|object_create|unit_kill/);
});
test('exact unoccupied healthy target and blast clearance permit the scoped probe',()=>{
  assert.equal(guardDestructionTarget(snapshot,players,[body,tank],volume).handle,target);
});
test('nearby player, occupied target, damaged tank and other root within blast guard reject',()=>{
  const near={...snapshot,players:[{...snapshot.players[0],position:[90,0,0]}]};
  assert.throws(()=>guardDestructionTarget(near,players,[body,tank],volume),/60m/);
  assert.throws(()=>guardDestructionTarget(snapshot,players,[body,{...tank,healthPercent:99}],volume),/healthy/);
  assert.throws(()=>guardDestructionTarget(snapshot,players,[body,tank,{handle:99,kind:'biped',parent:target,player:''}],volume),/occupied/);
  assert.throws(()=>guardDestructionTarget(snapshot,players,[body,tank,{...tank,handle:100,position:[110/3.048,0,0]}],volume),/blast-clearance/);
});
test('rounded zero percent cannot prove death; exact salted float32 health is required',()=>{
  const exact=fraction=>{
    const bytes=new DataView(new ArrayBuffer(4));bytes.setFloat32(0,fraction,true);
    return{schema:'mjolnir-object-health-v1',handle:target,kind:'vehicle',body_section_present:true,
      body_fraction:bytes.getFloat32(0,true),body_fraction_bits:bytes.getUint32(0,true),maximum_body:600};
  };
  assert.equal(Math.round(.004*100),0);
  assert.equal(bodyDepleted(exact(.004),target),false);
  assert.equal(bodyDepleted(exact(0),target),true);
  assert.throws(()=>bodyDepleted(exact(0),target+1),/Invalid/);
  assert.throws(()=>bodyDepleted({...exact(.004),body_fraction:0},target),/disagree/);
  assert.throws(()=>bodyDepleted({...exact(0),body_section_present:false},target),/Invalid/);
});
