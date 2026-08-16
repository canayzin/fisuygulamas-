from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from advanced_batch import (
    FailureStore,
    PendingBatchStore,
    SessionStore,
    build_balanced_print_jobs,
    build_filtered_jobs,
    build_matrix_status,
    check_integrity,
    filter_pending_jobs,
    get_last_receipt_number_for_firm,
    get_last_receipt_numbers,
    remove_jobs,
)
from complete_batch import PrintHistory, build_missing_firm_receipt_jobs


@dataclass
class Firm:
    firm_id: str
    name: str


class AdvancedBatchTests(unittest.TestCase):
    def setUp(self):
        self.a = Firm("A", "A")
        self.b = Firm("B", "B")
        self.c = Firm("C", "C")

    def test_missing_finder(self):
        jobs = build_missing_firm_receipt_jobs(
            [self.a, self.b, self.c],
            54,
            56,
            {("A", 54), ("B", 55)},
            False,
        )

        self.assertEqual(
            {job.pair_key for job in jobs},
            {
                ("B", 54),
                ("C", 54),
                ("A", 55),
                ("C", 55),
                ("A", 56),
                ("B", 56),
                ("C", 56),
            },
        )

    def test_last_receipt_numbers(self):
        history = {
            ("A", 54),
            ("A", 55),
            ("A", 70),
            ("B", 54),
        }

        self.assertEqual(
            get_last_receipt_numbers(history),
            {
                "A": 70,
                "B": 54,
            },
        )

        self.assertEqual(
            get_last_receipt_number_for_firm(
                "A",
                history,
            ),
            70,
        )

        self.assertIsNone(
            get_last_receipt_number_for_firm(
                "C",
                history,
            )
        )

    def test_matrix_status(self):
        matrix = build_matrix_status(
            [self.a],
            54,
            56,
            {("A", 54)},
            {("A", 55)},
        )

        self.assertEqual(
            matrix,
            {
                ("A", 54): "printed",
                ("A", 55): "failed",
                ("A", 56): "missing",
            },
        )

    def test_balanced_planner_prioritizes_less_used_firm(self):
        used = (
            {("A", no) for no in range(100)}
            | {("B", no) for no in range(50)}
        )

        jobs = build_balanced_print_jobs(
            [self.a, self.b],
            100,
            20,
            used,
        )

        self.assertTrue(
            all(
                job.firm_id == "B"
                for job in jobs
            )
        )

        self.assertEqual(
            len(
                {
                    job.pair_key
                    for job in jobs
                }
            ),
            20,
        )

    def test_failure_retry_lifecycle_does_not_mark_history_early(self):
        with tempfile.TemporaryDirectory() as directory:
            history = PrintHistory(
                Path(directory)
                / "history.json"
            )

            failures = FailureStore(
                Path(directory)
                / "failures.json"
            )

            failures.record(
                ("A", 54),
                "offline",
                "s1",
            )

            self.assertNotIn(
                ("A", 54),
                history.load_pairs(),
            )

            self.assertIn(
                ("A", 54),
                failures.active_pairs(),
            )

            history.record_printed(
                ("A", 54)
            )

            failures.resolve(
                ("A", 54)
            )

            self.assertIn(
                ("A", 54),
                history.load_pairs(),
            )

            self.assertNotIn(
                ("A", 54),
                failures.active_pairs(),
            )

    def test_pending_resume_filters_pairs_printed_elsewhere(self):
        jobs = build_missing_firm_receipt_jobs(
            [self.a],
            54,
            63,
            set(),
            False,
        )

        remaining = jobs[4:]

        used_elsewhere = {
            remaining[0].pair_key
        }

        resumed = filter_pending_jobs(
            remaining,
            used_elsewhere,
        )

        self.assertEqual(
            len(resumed),
            5,
        )

        self.assertNotIn(
            ("A", 58),
            {
                job.pair_key
                for job in resumed
            },
        )

    def test_preview_removal(self):
        jobs = build_missing_firm_receipt_jobs(
            [self.a, self.b],
            54,
            55,
            set(),
            False,
        )

        self.assertNotIn(
            jobs[1],
            remove_jobs(
                jobs,
                [1],
            ),
        )

    def test_filtered_safe_and_manual_reprint(self):
        used = {
            ("A", 54)
        }

        safe = build_filtered_jobs(
            [self.a, self.c],
            54,
            56,
            used,
            False,
        )

        manual = build_filtered_jobs(
            [self.a],
            54,
            54,
            used,
            True,
        )

        self.assertNotIn(
            ("A", 54),
            {
                job.pair_key
                for job in safe
            },
        )

        self.assertEqual(
            [
                job.pair_key
                for job in manual
            ],
            [
                ("A", 54)
            ],
        )

    def test_session_counters_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(
                Path(directory)
                / "sessions.json"
            )

            jobs = build_missing_firm_receipt_jobs(
                [self.a],
                54,
                55,
                set(),
                False,
            )

            session = store.create(
                "safe",
                jobs,
                54,
                55,
                False,
                skipped=3,
            )

            session.update(
                successful_count=1,
                failed_count=1,
                status="COMPLETED",
            )

            store.update(
                session
            )

            loaded = (
                store.list()[0]
            )

            self.assertEqual(
                (
                    loaded["planned_count"],
                    loaded["successful_count"],
                    loaded["failed_count"],
                    loaded["skipped_count"],
                ),
                (
                    2,
                    1,
                    1,
                    3,
                ),
            )

    def test_old_session_without_new_optional_fields_still_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "sessions.json"
            )

            path.write_text(
                '[{"session_id":"old","planned_count":1}]',
                encoding="utf-8",
            )

            self.assertEqual(
                SessionStore(path)
                .list()[0]["session_id"],
                "old",
            )

    def test_integrity_and_all_complete(self):
        firms = [
            Firm(
                str(index),
                str(index),
            )
            for index in range(20)
        ]

        all_pairs = {
            (
                firm.firm_id,
                no,
            )
            for firm in firms
            for no in range(100)
        }

        history = set(
            sorted(all_pairs)[:-2]
        )

        result = check_integrity(
            firms,
            0,
            99,
            history,
        )

        self.assertEqual(
            (
                result.expected,
                result.successful,
                result.missing,
            ),
            (
                2000,
                1998,
                2,
            ),
        )

        complete = check_integrity(
            firms,
            0,
            99,
            all_pairs,
        )

        self.assertEqual(
            complete.missing,
            0,
        )

    def test_pending_store_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PendingBatchStore(
                Path(directory)
                / "pending.json"
            )

            jobs = build_missing_firm_receipt_jobs(
                [self.a],
                54,
                55,
                set(),
                False,
            )

            store.save(
                "s1",
                "safe",
                jobs,
            )

            self.assertEqual(
                store.load()["pending"],
                [
                    ["A", 54],
                    ["A", 55],
                ],
            )

            store.clear()

            self.assertEqual(
                store.load(),
                {},
            )


if __name__ == "__main__":
    unittest.main()