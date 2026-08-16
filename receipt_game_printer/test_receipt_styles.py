from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import printer_service as printer_module
from printer_service import (
    NF_LOGO_BITMAP,
    PrinterService,
)
from receipt_formatter import (
    ReceiptData,
    build_receipt_text,
    build_styled_receipt,
)
from receipt_styles import (
    FirmReceiptStyleStore,
    StyleUndoManager,
    fit_styled_text,
    resolve_role_styles,
    validate_overrides,
)
from template_manager import default_template


@dataclass
class Firm:
    firm_id: str
    name: str
    game_code: str = ""


def sample_data(
    name: str = "A FIRMA",
) -> ReceiptData:
    return ReceiptData(
        firm_name=name,
        sector="SEKTOR",
        address="ADRES",
        game_code="G1",
        receipt_no=123,
        dt=datetime(
            2026,
            8,
            16,
            10,
            30,
        ),
        product_name="URUN",
        vat_rate=20,
        amount=5000,
        payment_type="NAKIT",
        address_line1="ADRES",
        phone1="0212 111 11 11",
        tax_office="VERGI",
        eku_no="001",
        z_no="707",
        footer_logo_code="JH 20018559",
    )


class FakeWriter:
    def __init__(self):
        self.writes: list[bytes] = []

    def WritePrinter(
        self,
        _handle,
        data: bytes,
    ):
        self.writes.append(data)


class ReceiptStyleTests(unittest.TestCase):
    def test_no_style_matches_legacy_text_exactly(self):
        template = default_template()

        self.assertEqual(
            build_styled_receipt(
                sample_data(),
                template,
                {},
            ).plain_text(),
            build_receipt_text(
                sample_data(),
                template,
            ),
        )

    def test_firm_name_bold_affects_only_firm_name(self):
        receipt = build_styled_receipt(
            sample_data(),
            default_template(),
            {
                "firm_name": {
                    "bold": True,
                }
            },
        )

        self.assertTrue(
            all(
                block.style.bold
                for block in receipt.blocks
                if block.role == "firm_name"
            )
        )

        # Yeni schema v2'de KDV satırı label/value olarak ayrılmıştır.
        self.assertFalse(
            any(
                block.style.bold
                for block in receipt.blocks
                if block.role
                in {
                    "vat_label",
                    "vat_amount",
                }
            )
        )

    def test_vat_scale_affects_only_vat(self):
        receipt = build_styled_receipt(
            sample_data(),
            default_template(),
            {
                "vat": {
                    "width_scale": 2,
                }
            },
        )

        # Parent "vat" override'ı schema v2 çocuklarına yayılmalı.
        self.assertTrue(
            all(
                block.style.width_scale == 2
                for block in receipt.blocks
                if block.role
                in {
                    "vat_label",
                    "vat_amount",
                }
            )
        )

        # TOPLAM bölümü bundan etkilenmemeli.
        self.assertTrue(
            all(
                block.style.width_scale == 1
                for block in receipt.blocks
                if block.role
                in {
                    "total_label",
                    "total_amount",
                }
            )
        )

    def test_styles_do_not_leak_between_firms(self):
        styled_a = build_styled_receipt(
            sample_data("A"),
            default_template(),
            {
                "firm_name": {
                    "bold": True,
                }
            },
        )

        styled_b = build_styled_receipt(
            sample_data("B"),
            default_template(),
            {},
        )

        self.assertTrue(
            next(
                block
                for block in styled_a.blocks
                if block.role == "firm_name"
            ).style.bold
        )

        self.assertFalse(
            next(
                block
                for block in styled_b.blocks
                if block.role == "firm_name"
            ).style.bold
        )

    def test_store_round_trip_partial_reset_and_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "styles.json"
            )

            a = Firm(
                "A",
                "A",
            )

            b = Firm(
                "B",
                "B",
            )

            store = FirmReceiptStyleStore(
                path
            )

            store.set(
                a,
                {
                    "vat": {
                        "bold": True,
                    }
                },
            )

            store.save()

            loaded = FirmReceiptStyleStore(
                path
            )

            loaded.load()

            self.assertEqual(
                loaded.get(a),
                {
                    "vat": {
                        "bold": True,
                    }
                },
            )

            loaded.copy_style(
                a,
                [b],
            )

            self.assertEqual(
                loaded.get(b),
                loaded.get(a),
            )

            # Firma datası style copy sırasında değişmemeli.
            self.assertEqual(
                b.name,
                "B",
            )

            loaded.set(
                a,
                {},
            )

            self.assertEqual(
                loaded.get(a),
                {},
            )

    def test_partial_profile_inherits_global_defaults(self):
        styles = resolve_role_styles(
            default_template(),
            {
                "vat": {
                    "bold": True,
                }
            },
        )

        self.assertTrue(
            styles["vat"].bold
        )

        self.assertTrue(
            styles["vat_label"].bold
        )

        self.assertTrue(
            styles["vat_amount"].bold
        )

        self.assertEqual(
            styles["total"].width_scale,
            1,
        )

        self.assertEqual(
            styles["total_amount"].width_scale,
            1,
        )

    def test_empty_profile_resets_store_to_global_default(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FirmReceiptStyleStore(
                Path(directory)
                / "styles.json"
            )

            firm = Firm(
                "A",
                "A",
            )

            store.set(
                firm,
                {
                    "vat": {
                        "bold": True,
                    }
                },
            )

            store.set(
                firm,
                {},
            )

            self.assertEqual(
                store.get(firm),
                {},
            )

    def test_copy_changes_only_target_style(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FirmReceiptStyleStore(
                Path(directory)
                / "styles.json"
            )

            source = Firm(
                "A",
                "Source",
            )

            target = Firm(
                "B",
                "Target",
            )

            store.set(
                source,
                {
                    "total": {
                        "bold": True,
                    }
                },
            )

            store.copy_style(
                source,
                [target],
            )

            self.assertEqual(
                target.name,
                "Target",
            )

            self.assertEqual(
                store.get(target),
                {
                    "total": {
                        "bold": True,
                    }
                },
            )

    def test_store_writes_versioned_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "styles.json"
            )

            store = FirmReceiptStyleStore(
                path
            )

            store.save()

            # Yeni gelişmiş Tasarım Stüdyosu schema sürümü.
            self.assertIn(
                '"version": 2',
                path.read_text(
                    encoding="utf-8"
                ),
            )

    def test_undo_and_redo(self):
        manager = StyleUndoManager(
            {}
        )

        manager.push(
            {
                "firm_name": {
                    "bold": True,
                }
            }
        )

        manager.push(
            {
                "firm_name": {
                    "bold": True,
                },
                "vat": {
                    "width_scale": 2,
                },
            }
        )

        self.assertNotIn(
            "vat",
            manager.undo(),
        )

        self.assertIn(
            "vat",
            manager.redo(),
        )

    def test_corrupt_json_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "styles.json"
            )

            path.write_text(
                "{broken",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "okunamadı",
            ):
                FirmReceiptStyleStore(
                    path
                ).load()

    def test_unsupported_scale_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "ölçeği",
        ):
            validate_overrides(
                {
                    "vat": {
                        "width_scale": 3,
                    }
                }
            )

    def test_unsupported_alignment_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "Hizalama",
        ):
            validate_overrides(
                {
                    "vat": {
                        "align": "diagonal",
                    }
                }
            )

    def test_visibility_hides_only_selected_role(self):
        receipt = build_styled_receipt(
            sample_data(),
            default_template(),
            {
                "phone": {
                    "visible": False,
                }
            },
        )

        # Schema v2'de phone parent override'ı phone1/phone2 çocuklarına yayılır.
        self.assertFalse(
            any(
                block.role
                in {
                    "phone",
                    "phone1",
                    "phone2",
                }
                for block in receipt.blocks
            )
        )

        self.assertTrue(
            any(
                block.role == "firm_name"
                for block in receipt.blocks
            )
        )

    def test_scaled_money_line_preserves_complete_amount(self):
        style = resolve_role_styles(
            default_template(),
            {
                "vat": {
                    "width_scale": 2,
                }
            },
        )["vat"]

        self.assertIn(
            "*5.000,00",
            fit_styled_text(
                "TOPKDV                 *5.000,00",
                style,
                32,
            ),
        )

    def test_current_profile_is_resolved_each_time_for_batch_paths(self):
        template = default_template()

        store_profile = {
            "total": {
                "height_scale": 2,
            }
        }

        first = build_styled_receipt(
            sample_data(),
            template,
            store_profile,
        )

        second = build_styled_receipt(
            sample_data(),
            template,
            {},
        )

        # Schema v2: total parent style, total_amount child role'üne yayılır.
        self.assertEqual(
            next(
                block
                for block in first.blocks
                if block.role
                == "total_amount"
            ).style.height_scale,
            2,
        )

        self.assertEqual(
            next(
                block
                for block in second.blocks
                if block.role
                == "total_amount"
            ).style.height_scale,
            1,
        )

    def test_escpos_bold_size_alignment_reset_and_cp857(self):
        template = replace(
            default_template(),
            show_footer_logo=False,
        )

        data = sample_data(
            "ÇAĞRI"
        )

        receipt = build_styled_receipt(
            data,
            template,
            {
                "firm_name": {
                    "bold": True,
                    "width_scale": 2,
                    "align": "center",
                }
            },
        )

        fake = FakeWriter()

        with patch.object(
            printer_module,
            "win32print",
            fake,
        ):
            PrinterService()._write_styled_receipt(
                "HANDLE",
                receipt,
            )

        written = b"".join(
            fake.writes
        )

        self.assertIn(
            b"\x1bE\x01",
            written,
        )

        self.assertIn(
            b"\x1d!\x10",
            written,
        )

        self.assertIn(
            b"\x1ba\x01",
            written,
        )

        self.assertIn(
            b"\x1bE\x00"
            b"\x1d!\x00"
            b"\x1ba\x00",
            written,
        )

        self.assertIn(
            "ÇAĞRI"[:16].encode(
                "cp857",
                errors="replace",
            ),
            written,
        )

    def test_nf_bitmap_constant_and_placeholder_rendering_remain_active(self):
        before = tuple(
            NF_LOGO_BITMAP
        )

        receipt = build_styled_receipt(
            sample_data(),
            default_template(),
            {
                "footer_logo": {
                    "align": "right",
                }
            },
        )

        fake = FakeWriter()

        with patch.object(
            printer_module,
            "win32print",
            fake,
        ):
            PrinterService()._write_styled_receipt(
                "HANDLE",
                receipt,
            )

        written = b"".join(
            fake.writes
        )

        # NF geometrisi değişmemeli.
        self.assertEqual(
            before,
            NF_LOGO_BITMAP,
        )

        # Internal placeholder gerçek yazıcıya metin olarak gitmemeli.
        self.assertNotIn(
            b"[NF LOGO]",
            written,
        )

        # ESC * 24-dot bitmap komutu kullanılmaya devam etmeli.
        self.assertTrue(
            any(
                chunk.startswith(
                    b"\x1b*\x21"
                )
                for chunk in fake.writes
            )
        )


if __name__ == "__main__":
    unittest.main()