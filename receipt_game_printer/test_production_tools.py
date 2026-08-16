from __future__ import annotations

import random
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from backup_manager import BackupManager
from production_tools import (
    FinancialSummary,
    build_dry_run,
    build_normal_batch_plan,
    generate_amount,
    generate_smart_amounts,
    run_preflight,
    search_records,
)


@dataclass
class Firm:
    firm_id: str
    name: str
    default_amount: float = 1000


class ProductionToolsTests(unittest.TestCase):
    def setUp(self):
        self.firms = [
            Firm("A", "A"),
            Firm("B", "B"),
            Firm("C", "C"),
        ]

    def test_fifty_step_amounts(self):
        rng = random.Random(4)

        self.assertTrue(
            all(
                generate_amount(
                    2100,
                    3600,
                    50,
                    rng,
                )
                % 50
                == 0
                for _ in range(100)
            )
        )

        self.assertEqual(
            generate_amount(
                2125,
                2180,
                50,
                rng,
            ),
            2150,
        )

        with self.assertRaises(ValueError):
            generate_amount(
                2121,
                2149,
                50,
                rng,
            )

    def test_smart_distribution_uses_all_thirds_and_step(self):
        amounts = generate_smart_amounts(
            100,
            1000,
            10000,
            50,
            random.Random(7),
        )

        buckets = [
            0,
            0,
            0,
        ]

        for value in amounts:
            self.assertEqual(
                value % 50,
                0,
            )

            buckets[
                min(
                    int(
                        (
                            value
                            - 1000
                        )
                        / 3000
                    ),
                    2,
                )
            ] += 1

        self.assertTrue(
            all(
                count > 0
                for count in buckets
            )
        )

    def test_max_per_firm_and_exclusion(self):
        with self.assertRaisesRegex(
            ValueError,
            "maksimum 9",
        ):
            build_normal_batch_plan(
                self.firms,
                10,
                1,
                "Rastgele",
                max_per_firm=3,
            )

        plan = build_normal_batch_plan(
            self.firms,
            6,
            1,
            "Rastgele",
            excluded_firm_ids={"B"},
            max_per_firm=3,
            fixed_amount=1000,
            rng=random.Random(2),
        )

        self.assertNotIn(
            "B",
            {
                item.job.firm_id
                for item in plan
            },
        )

        self.assertTrue(
            all(
                sum(
                    1
                    for item in plan
                    if item.job.firm_id
                    == firm_id
                )
                <= 3
                for firm_id in (
                    "A",
                    "C",
                )
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "Bütün firmalar",
        ):
            build_normal_batch_plan(
                self.firms,
                1,
                1,
                "Sırayla",
                excluded_firm_ids={
                    "A",
                    "B",
                    "C",
                },
            )

    def test_financial_summary_counts_only_success_and_retry_once(self):
        summary = FinancialSummary()

        summary.add_success(
            "A54",
            "A",
            "A",
            5000,
            20,
        )

        summary.add_success(
            "A55",
            "A",
            "A",
            5000,
            20,
        )

        self.assertFalse(
            summary.add_success(
                "A55",
                "A",
                "A",
                5000,
                20,
            )
        )

        totals = summary.totals()

        self.assertEqual(
            totals["count"],
            2,
        )

        self.assertEqual(
            float(
                totals[
                    "total_amount"
                ]
            ),
            10000,
        )

        # Yeni merkezi KDV kuralı:
        # 5000 × %20 = 1000
        # 2 başarılı fiş = 2000 toplam KDV.
        self.assertAlmostEqual(
            float(
                totals[
                    "total_vat"
                ]
            ),
            2000.00,
            places=2,
        )

    def test_preflight_errors_and_dry_run_warning(self):
        bad = run_preflight(
            printer_name="",
            printer_exists=lambda _name: False,
            firms=[],
            requested_count=1,
            start_no=2,
            end_no=1,
            minimum_amount=2121,
            maximum_amount=2149,
            step_mode=50,
            max_per_firm=None,
            excluded_count=0,
            history_loader=lambda: set(),
            batch_active=False,
            pending_active=False,
            template_validator=lambda: None,
            bitmap_ready=True,
        )

        self.assertGreaterEqual(
            len(
                bad.errors
            ),
            4,
        )

        dry = run_preflight(
            printer_name="",
            printer_exists=lambda _name: False,
            firms=self.firms,
            requested_count=1,
            start_no=1,
            end_no=1,
            minimum_amount=100,
            maximum_amount=200,
            step_mode=50,
            max_per_firm=None,
            excluded_count=0,
            history_loader=lambda: set(),
            batch_active=False,
            pending_active=True,
            template_validator=lambda: None,
            bitmap_ready=True,
            dry_run=True,
        )

        self.assertTrue(
            dry.ok
        )

        self.assertTrue(
            dry.warnings
        )

        # Bilerek yanlış KDV verilirse preflight baskıya izin vermemeli.
        vat_bad = run_preflight(
            printer_name="P",
            printer_exists=lambda _name: True,
            firms=self.firms,
            requested_count=1,
            start_no=1,
            end_no=1,
            minimum_amount=5000,
            maximum_amount=5000,
            step_mode=None,
            max_per_firm=None,
            excluded_count=0,
            history_loader=lambda: set(),
            batch_active=False,
            pending_active=False,
            template_validator=lambda: None,
            bitmap_ready=True,
            vat_checks=[
                (
                    5000,
                    20,
                    833.33,
                )
            ],
        )

        self.assertFalse(
            vat_bad.ok
        )

        self.assertIn(
            "KDV doğrulaması başarısız",
            vat_bad.errors[0],
        )

    def test_search_filters(self):
        records = [
            {
                "firm_id": "A",
                "firm_name": "Alpha",
                "receipt_no": 54,
                "amount": 1000,
                "session_id": "s1",
                "status": "successful",
                "mode": "normal",
            },
            {
                "firm_id": "B",
                "firm_name": "Beta",
                "receipt_no": 70,
                "amount": 5000,
                "session_id": "s2",
                "status": "failed",
                "mode": "advanced",
            },
        ]

        self.assertEqual(
            len(
                search_records(
                    records,
                    firm="alp",
                    start_no=50,
                    end_no=60,
                    min_amount=900,
                    max_amount=1100,
                    session_id="s1",
                    status="successful",
                    mode="normal",
                )
            ),
            1,
        )

    def test_backup_restore_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(
                directory
            )

            (
                base
                / "firms.json"
            ).write_text(
                '[{"name":"old"}]',
                encoding="utf-8",
            )

            manager = BackupManager(
                base,
                [
                    "firms.json"
                ],
                retention=20,
            )

            backup = manager.create(
                "test"
            )

            (
                base
                / "firms.json"
            ).write_text(
                '[{"name":"new"}]',
                encoding="utf-8",
            )

            emergency = manager.restore(
                backup
            )

            self.assertIn(
                "old",
                (
                    base
                    / "firms.json"
                ).read_text(
                    encoding="utf-8"
                ),
            )

            self.assertTrue(
                emergency.exists()
            )

            (
                backup
                / "firms.json"
            ).write_text(
                "broken",
                encoding="utf-8",
            )

            with self.assertRaises(
                ValueError
            ):
                manager.restore(
                    backup
                )

    def test_dry_run_uses_real_plan_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            history = (
                Path(directory)
                / "print_history.json"
            )

            failures = (
                Path(directory)
                / "print_failures.json"
            )

            pending = (
                Path(directory)
                / "pending_batch.json"
            )

            printer_calls = []

            plan = build_normal_batch_plan(
                self.firms,
                3,
                54,
                "Sırayla",
                fixed_amount=1000,
            )

            dry = build_dry_run(
                plan,
                0,
                [],
                20,
            )

            self.assertEqual(
                [
                    item.job.pair_key
                    for item in dry.planned_jobs
                ],
                [
                    item.job.pair_key
                    for item in plan
                ],
            )

            self.assertEqual(
                len(
                    dry.financial_summary
                ),
                3,
            )

            self.assertEqual(
                printer_calls,
                [],
            )

            self.assertFalse(
                any(
                    path.exists()
                    for path in (
                        history,
                        failures,
                        pending,
                    )
                )
            )


if __name__ == "__main__":
    unittest.main()