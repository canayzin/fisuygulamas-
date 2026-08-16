from __future__ import annotations

import random
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from complete_batch import PrintHistory, build_missing_firm_receipt_jobs


@dataclass
class TestFirm:
    firm_id: str
    name: str
    game_code: str = ""


def pair_keys(jobs):
    return [job.pair_key for job in jobs]


class CompleteBatchTests(unittest.TestCase):
    def setUp(self):
        self.a = TestFirm("A", "Firma A")
        self.b = TestFirm("B", "Firma B")
        self.c = TestFirm("C", "Firma C")

    def test_cartesian_product_contains_nine_unique_pairs(self):
        jobs = build_missing_firm_receipt_jobs([self.a, self.b, self.c], 54, 56, set(), False)
        self.assertEqual(len(jobs), 9)
        self.assertEqual(len(set(pair_keys(jobs))), 9)
        for firm_id in ("A", "B", "C"):
            self.assertEqual({job.receipt_no for job in jobs if job.firm_id == firm_id}, {54, 55, 56})

    def test_used_pair_is_skipped_but_other_pairs_remain(self):
        jobs = build_missing_firm_receipt_jobs([self.a, self.b], 54, 55, {("A", 54)}, False)
        self.assertEqual(pair_keys(jobs), [("B", 54), ("A", 55), ("B", 55)])

    def test_one_firms_number_does_not_block_another_firm(self):
        jobs = build_missing_firm_receipt_jobs([self.a, self.b], 54, 54, {("A", 54)}, False)
        self.assertEqual(pair_keys(jobs), [("B", 54)])

    def test_generated_pairs_are_never_duplicated(self):
        jobs = build_missing_firm_receipt_jobs([self.a, self.a, self.b], 54, 55, set(), False)
        self.assertEqual(len(jobs), len(set(pair_keys(jobs))))

    def test_randomization_changes_only_order(self):
        ordered = build_missing_firm_receipt_jobs([self.a, self.b, self.c], 54, 56, set(), False)
        shuffled = build_missing_firm_receipt_jobs(
            [self.a, self.b, self.c], 54, 56, set(), True, random.Random(7)
        )
        self.assertEqual(set(pair_keys(ordered)), set(pair_keys(shuffled)))
        self.assertNotEqual(pair_keys(ordered), pair_keys(shuffled))

    def test_all_used_returns_empty_list(self):
        used = {(firm_id, no) for firm_id in ("A", "B") for no in (54, 55)}
        self.assertEqual(build_missing_firm_receipt_jobs([self.a, self.b], 54, 55, used, False), [])

    def test_single_number_builds_one_job_per_firm(self):
        firms = [TestFirm(str(index), f"Firma {index}") for index in range(10)]
        jobs = build_missing_firm_receipt_jobs(firms, 60, 60, set(), False)
        self.assertEqual(len(jobs), 10)
        self.assertTrue(all(job.receipt_no == 60 for job in jobs))
        self.assertEqual(len({job.firm_id for job in jobs}), 10)

    def test_start_after_end_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Başlangıç"):
            build_missing_firm_receipt_jobs([self.a], 61, 60, set(), False)

    def test_empty_firm_list_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Firma listesi boş"):
            build_missing_firm_receipt_jobs([], 54, 55, set(), False)

    def test_duplicate_firm_ids_create_only_one_pair(self):
        duplicate = TestFirm("A", "Firma A kopyası")
        jobs = build_missing_firm_receipt_jobs([self.a, duplicate], 54, 54, set(), False)
        self.assertEqual(pair_keys(jobs), [("A", 54)])

    def test_history_persists_and_rejects_duplicate_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            history = PrintHistory(Path(directory) / "print_history.json")
            self.assertTrue(history.record_printed(("A", 54)))
            self.assertFalse(history.record_printed(("A", 54)))
            self.assertTrue(history.record_printed(("B", 54)))
            self.assertEqual(history.load_pairs(), {("A", 54), ("B", 54)})

    def test_corrupt_history_is_reported_instead_of_silently_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "print_history.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Baskı geçmişi okunamadı"):
                PrintHistory(path).load_pairs()


if __name__ == "__main__":
    unittest.main()
