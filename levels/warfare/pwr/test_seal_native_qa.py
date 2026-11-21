import copy
import json
from pathlib import Path
import tempfile
import unittest

from vehicle_spawn_policy import load_policy, transform, POLICY, sha, validate_level
from check_native_contract import load_frozen_contract
from seal_native_qa import check_prepared_level, record, write_new


class SealGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.plan = Path(self.temp.name)/'plan.json'
        self.points = [{'flag': 'terrain_probe_'+str(i), 'position_m': [i, 2*i, 3*i], 'yaw': 20*i} for i in range(12)]
        self.plan.write_text(json.dumps({'schema':'pwr-terrain-probe-v1','protocol':20569,'layout_revision':3,'probes':self.points}))
        self.level = transform(load_frozen_contract()[2], load_policy())
        self.level['blam']['cutscene_flags'] += [{'name':p['flag'], 'pos':[100*p['position_m'][0], -100*p['position_m'][1], 100*p['position_m'][2]], 'yaw':p['yaw']} for p in self.points]
        self.level['blam']['cutscene_flags'].append({'name':'terrain_probe_hash_'+sha(self.plan)[:12], 'pos':[1100,-2200,3300], 'yaw':0})
        self.contract = {'layout3_permitted':True,'terrain_contract_compatible':True,
                         'vehicle_spawn_policy':validate_level(self.level)[1], 'probe_plan_sha256':sha(self.plan)}

    def test_explicit_policy_and_matching_fresh_probe_are_required(self):
        check_prepared_level(self.level,POLICY,self.contract,self.plan)
        with self.assertRaisesRegex(ValueError,'explicitly'):
            check_prepared_level(self.level,POLICY,{**self.contract,'vehicle_spawn_policy':None},self.plan)
        self.plan.write_text('changed plan')
        with self.assertRaisesRegex(ValueError,'fresh compiled'):
            check_prepared_level(self.level,POLICY,self.contract,self.plan)

    def test_policy_cannot_hide_unrelated_installed_gameplay_change(self):
        bad=copy.deepcopy(self.level)
        bad['blam']['vehicles'][0]['yaw']+=1
        with self.assertRaisesRegex(ValueError,'native gameplay'):
            check_prepared_level(bad,POLICY,self.contract,self.plan)

    def test_valid_hash_stamp_cannot_hide_missing_moved_rotated_or_extra_probes(self):
        for change in ('missing','position','yaw','extra','stamp_only'):
            bad=copy.deepcopy(self.level)
            flags=bad['blam']['cutscene_flags']
            probe=next(p for p in flags if p['name']=='terrain_probe_0')
            if change=='missing': flags.remove(probe)
            elif change=='position': probe['pos'][0]+=1
            elif change=='yaw': probe['yaw']+=1
            elif change=='extra': flags.append({'name':'terrain_probe_old', 'pos':[1,2,3], 'yaw':0})
            else: bad['blam']['cutscene_flags']=[p for p in flags if not p['name'].startswith('terrain_probe_') or p['name'].startswith('terrain_probe_hash_')]
            with self.subTest(change=change), self.assertRaisesRegex(ValueError,'compiled probe geometry'):
                check_prepared_level(bad,POLICY,self.contract,self.plan)

    def test_artifact_changes_and_evidence_overwrite_reject(self):
        path=Path(self.temp.name)/'proof.json'
        write_new(path,{'pass':True})
        original=record(path)
        with self.assertRaises(FileExistsError): write_new(path,{'pass':False})
        path.write_text('changed')
        with self.assertRaisesRegex(ValueError,'differs from receipt'):record(path,original['sha256'])


if __name__=='__main__':unittest.main()
