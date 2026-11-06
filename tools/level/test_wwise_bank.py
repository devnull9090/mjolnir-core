#!/usr/bin/env python3
"""wwise_bank.py on made-up records. Shipped banks stay out of the repository, so
what a real template gives is checked by the build, not here."""
import hashlib
import struct
import unittest

import wwise_bank as W


def ranges():
    return [{"name": "idle", "natural": 1.1, "low": 1.0, "high": 1.1},
            {"name": "low", "natural": 1.38, "low": 1.1, "high": 1.5},
            {"name": "high", "natural": 2.0, "low": 1.5, "high": 2.0}]


class Ids(unittest.TestCase):
    def test_a_name_hashes_as_wwise_does(self):
        self.assertEqual(W.RTPC_SPEED, 162356596)
        self.assertEqual(W.fnv1("RTPC_VEH_Speed"), W.fnv1("rtpc_veh_speed"))

    def test_two_maps_share_no_id(self):
        one = W.engine_ids("MJ_RWC_Mongoose_Engine", ranges())
        two = W.engine_ids("MJ_YOY_Mongoose_Engine", ranges())
        self.assertFalse(set(one.values()) & set(two.values()))

    def test_every_id_of_a_bank_is_its_own(self):
        ids = W.engine_ids("MJ_RWC_Mongoose_Engine", ranges())
        self.assertEqual(len(set(ids.values())), len(ids))


class Blend(unittest.TestCase):
    def test_the_first_range_has_no_floor_and_the_last_no_ceiling(self):
        r = ranges()
        self.assertEqual(W.share(0.5, r[0], True, False), 1.0)
        self.assertEqual(W.share(9.0, r[2], False, True), 1.0)

    def test_two_ranges_cross_at_their_bound(self):
        r = ranges()
        self.assertAlmostEqual(W.share(1.1, r[0], True, False), 0.5)
        self.assertAlmostEqual(W.share(1.1, r[1], False, False), 0.5)

    def test_a_range_is_silent_away_from_its_band(self):
        r = ranges()
        self.assertEqual(W.share(1.8, r[1], False, False), 0.0)

    def test_at_rest_only_the_first_range_sounds(self):
        ids = W.engine_ids("x", ranges())
        r = ranges()
        firsts = [W.range_curves(x, i, len(r), (1.0, 2.0), ids)[2][0] for i, x in enumerate(r)]
        self.assertEqual([y for _, y in firsts], [0.0, -1.0, -1.0])

    def test_pitch_runs_from_ce_low_to_high_about_the_sample(self):
        ids = W.engine_ids("x", ranges())
        points = W.range_curves(ranges()[2], 2, 3, (1.0, 2.0), ids)[1]
        self.assertAlmostEqual(points[0][1], -1200.0)
        self.assertAlmostEqual(points[-1][1], 0.0)


class Records(unittest.TestCase):
    def test_children_replaces_the_list_that_ends_a_body(self):
        body = b"\xAA" * 12 + struct.pack("<III", 2, 5, 9)
        out = W.children(body, [30, 20, 10])
        self.assertEqual(out, b"\xAA" * 12 + struct.pack("<IIII", 3, 10, 20, 30))

    def test_a_body_with_no_list_is_refused(self):
        with self.assertRaises(ValueError):
            W.children(b"\xFF" * 40, [1])

    def test_a_curve_keeps_its_points_in_order(self):
        record = W.curve(W.RTPC_SPEED, W.PARAM_PITCH, 7, 0, [(0.0, -100.0), (1.0, 100.0)])
        self.assertEqual(struct.unpack_from("<I", record, 0)[0], W.RTPC_SPEED)
        self.assertEqual(struct.unpack_from("<ffI", record, 14), (0.0, -100.0, W.LINEAR))
        self.assertEqual(len(record), 14 + 24)

    def test_a_bank_reads_back_and_data_starts_on_16(self):
        small = b"BKHD" + struct.pack("<I", 40) + bytes(40)
        blobs = {7: b"seven", 3: b"three!"}
        bank = W.assemble(small, 99, [W.obj(2, 11, b"body")], blobs)
        found = W.sections(bank)
        self.assertEqual(list(found), [b"BKHD", b"DIDX", b"DATA", b"HIRC"])
        self.assertEqual(found[b"DATA"][0] % 16, 0)
        self.assertEqual(struct.unpack_from("<I", bank, found[b"BKHD"][0] + 4)[0], 99)
        self.assertEqual(W.media(bank, 7), b"seven")
        self.assertEqual(W.media(bank, 3), b"three!")
        self.assertEqual(W.objects(bank), {11: (2, b"body")})
        with self.assertRaises(KeyError):
            W.media(bank, 1)


class Pak(unittest.TestCase):
    def footer(self, pak):
        at = len(pak) - 221
        magic, version, index, size = struct.unpack_from("<IIQQ", pak, at + 17)
        return magic, version, index, size

    def test_a_pak_has_shipped_paks_footer(self):
        pak = W.bank_pak("pakchunk996-MJOLNIRBANK-RWC_P", {5: b"bank"})
        magic, version, index, size = self.footer(pak)
        self.assertEqual((magic, version), (0x5A6F12E1, 11))
        self.assertLess(index + size, len(pak))

    def test_a_pak_holds_each_bank_under_its_id(self):
        pak = W.bank_pak("c", {5: b"first bank", 6: b"second"})
        self.assertIn(b"5.bnk\0", pak)
        self.assertIn(b"6.bnk\0", pak)
        self.assertIn(b"first bank", pak)
        self.assertIn(b"Meteorite/Content/WwiseAudio/", pak)

    def test_a_pak_matches_the_launchers_bytes(self):
        # crates/ue-iostore/src/bank.rs asserts the same hash: the launcher writes
        # these for a hub install, so the two writers have to stay together.
        pak = W.bank_pak("pakchunk996-MJOLNIRBANK-RWC_P", {6: b"second bank", 5: b"first"})
        self.assertEqual(hashlib.sha1(pak).hexdigest(), "b7db7dc0eb5e7cd546a76ab228cc2670bc9e16a3")

    def test_the_same_container_gives_the_same_bytes(self):
        banks = {5: b"bank"}
        self.assertEqual(W.bank_pak("c", banks), W.bank_pak("c", banks))
        self.assertNotEqual(W.bank_pak("c", banks), W.bank_pak("d", banks))


if __name__ == "__main__":
    unittest.main()
