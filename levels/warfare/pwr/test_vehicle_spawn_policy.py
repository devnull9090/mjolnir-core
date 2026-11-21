import copy
import json
from pathlib import Path
import tempfile
import unittest

import vehicle_spawn_policy as policy
from check_native_contract import load_frozen_contract, assert_equal, gameplay_level


class VehicleSpawnCorrectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = policy.load_policy()
        cls.frozen = load_frozen_contract()[2]

    def test_only_eight_vehicle_and_four_probe_heights_change(self):
        after = policy.transform(self.frozen, self.doc)
        changed = []
        for collection in ('vehicles', 'trigger_volumes'):
            before_rows = {row.get('name'):row for row in self.frozen['blam'][collection]}
            for row in after['blam'][collection]:
                old = before_rows[row.get('name')]
                if row != old:
                    self.assertEqual(row['pos'][:2], old['pos'][:2])
                    restored = copy.deepcopy(row); restored['pos'] = old['pos']
                    self.assertEqual(restored, old)
                    changed.append(collection)
        self.assertEqual(changed.count('vehicles'), 8)
        self.assertEqual(changed.count('trigger_volumes'), 4)
        self.assertEqual(policy.transform(after, self.doc, revert=True), self.frozen)

    def test_correction_is_idempotent_but_contract_requires_applied_policy(self):
        after = policy.transform(self.frozen, self.doc)
        self.assertEqual(policy.transform(after, self.doc), after)
        with self.assertRaisesRegex(ValueError, 'requires the corrected'):
            policy.transform(self.frozen, self.doc, revert=True)

    def test_changed_timer_xy_or_partial_patch_fails_closed(self):
        name = self.doc['vehicles'][0]['name']
        for mutation in ('timer', 'xy', 'partial'):
            bad = copy.deepcopy(self.frozen)
            row = policy.unique(bad['blam']['vehicles'], name)
            if mutation == 'timer': row['set']['multiplayer data.abandonment time'] = '180'
            elif mutation == 'xy': row['pos'][0] += 1
            else: row['pos'] = self.doc['vehicles'][0]['new_pos_cm']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                policy.transform(bad, self.doc)

    def test_other_native_fields_still_require_exact_frozen_equality(self):
        after = policy.transform(self.frozen, self.doc)
        after['blam']['vehicles'][0]['yaw'] += 1
        normalized, _ = policy.validate_level(after)
        with self.assertRaises(ValueError):
            assert_equal(self.frozen, gameplay_level(normalized), 'scenario')

    def test_support_clearance_has_large_native_threshold_margin(self):
        self.assertEqual(policy.ABANDON_DISTANCE_M, 1.524)
        for row in self.doc['vehicles']:
            self.assertAlmostEqual(row['new_pos_cm'][2]/100-row['support_floor_m'], .9, places=7)
            self.assertGreater(row['expected_initial_settling_m'], .1)
            self.assertLess(row['expected_initial_settling_m'], .75)
            self.assertGreater(row['distance_threshold_margin_m'], .75)

    def test_edited_policy_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'changed.json'
            path.write_text(json.dumps(self.doc, indent=1))
            with self.assertRaisesRegex(ValueError, 'sealed correction'):
                policy.load_policy(path)

    def test_generated_support_and_evidence_still_match_sealed_policy(self):
        self.assertEqual(policy.generate(), self.doc)

    def test_proposal_preserves_source_and_rejects_overwrite_or_unrelated_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp)/'source.json', Path(temp)/'proposal.json'
            source.write_text(json.dumps(self.frozen))
            before = source.read_bytes()
            with self.assertRaisesRegex(ValueError, 'independent output'):
                policy.patch_file(source, source)
            receipt = policy.patch_file(source, output)
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse(receipt['installed'])
            self.assertEqual(policy.read(output), policy.transform(self.frozen, self.doc))
            with self.assertRaisesRegex(ValueError, 'already exists'):
                policy.patch_file(source, output)
            bad = copy.deepcopy(self.frozen)
            bad['blam']['vehicles'][0]['yaw'] += 1
            source.write_text(json.dumps(bad))
            rejected = Path(temp)/'rejected.json'
            with self.assertRaises(ValueError):
                policy.patch_file(source, rejected)
            self.assertFalse(rejected.exists())


if __name__ == '__main__': unittest.main()
