from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, replace
from pathlib import Path
from unittest.mock import Mock, patch

import printer_service as printer_module
from printer_service import NF_LOGO_BITMAP, PrinterService
from receipt_formatter import build_styled_receipt
from receipt_styles import FirmReceiptStyleStore, ReceiptBlock, TextStyle, apply_styles, fit_styled_text
from template_manager import default_template
from test_receipt_styles import FakeWriter, sample_data
from vat_engine import calculate_vat, validated_print, validate_vat_integrity


@dataclass
class Firm:
    firm_id: str
    name: str


class VatAndLayoutTests(unittest.TestCase):
    def test_project_vat_rule_examples(self):
        cases = [(5000, 20, "1000.00"), (3750, 20, "750.00"), (3000, 20, "600.00"),
                 (8000, 20, "1600.00"), (10000, 18, "1800.00"), (2500, 10, "250.00"),
                 (1000, 1, "10.00"), (3550, 20, "710.00")]
        for amount, rate, expected in cases:
            with self.subTest(amount=amount, rate=rate):
                self.assertEqual(str(calculate_vat(amount, rate)), expected)
        self.assertNotEqual(calculate_vat(5000, 20), 833.33)

    def test_wrong_vat_blocks_hardware_call(self):
        printer = Mock()
        with self.assertRaisesRegex(ValueError, "KDV doğrulaması başarısız"):
            validated_print(printer, "P", "receipt", 5000, 20, 833.33)
        printer.print_raw.assert_not_called()

    def test_wrong_vat_embedded_in_receipt_is_detected(self):
        printer = Mock()
        with self.assertRaisesRegex(ValueError, "833.33"):
            validated_print(printer, "P", "TOPKDV *833,33\nTOPLAM *5.000,00", 5000, 20)
        printer.print_raw.assert_not_called()

    def test_correct_vat_allows_hardware_call(self):
        printer = Mock()
        validated_print(printer, "P", "receipt", 5000, 20, 1000)
        printer.print_raw.assert_called_once_with("P", "receipt")

    def test_studio_receipt_contains_correct_vat(self):
        text = build_styled_receipt(sample_data(), default_template(), {}).plain_text()
        self.assertIn("TOPKDV                 *1.000,00", text)

    def test_logo_and_code_are_written_before_newline(self):
        fake = FakeWriter()
        service = PrinterService()
        before = tuple(NF_LOGO_BITMAP)
        with patch.object(printer_module, "win32print", fake):
            service.print_bitmap_logo("H", "JH 20018559")
        bitmap_index = next(i for i, value in enumerate(fake.writes) if value.startswith(b"\x1b*\x21"))
        code_index = next(i for i, value in enumerate(fake.writes) if b"JH 20018559" in value)
        newline_index = next(i for i, value in enumerate(fake.writes) if value.startswith(b"\n"))
        self.assertLess(bitmap_index, code_index)
        self.assertLess(code_index, newline_index)
        self.assertIn(b"  JH 20018559", fake.writes[code_index])
        self.assertEqual(before, NF_LOGO_BITMAP)

    def test_logo_offsets_and_gap_generate_positioned_output(self):
        fake = FakeWriter()
        style = TextStyle(logo_x_offset=4, logo_y_offset=-2, code_gap=4, code_x_offset=3)
        with patch.object(printer_module, "win32print", fake):
            PrinterService().print_bitmap_logo("H", "AS0000084145", "center", style)
        self.assertTrue(any(value.startswith(b"\x1b\\") for value in fake.writes))
        self.assertIn(b"    AS0000084145", fake.writes)

    def test_big_vat_resets_before_normal_total(self):
        receipt = build_styled_receipt(sample_data(), default_template(), {"vat_amount": {"height_scale": 2}})
        fake = FakeWriter()
        with patch.object(printer_module, "win32print", fake):
            PrinterService()._write_styled_receipt("H", receipt)
        joined = b"".join(fake.writes)
        self.assertIn(b"\x1d!\x01", joined)
        self.assertIn(b"\x1bE\x00\x1d!\x00\x1ba\x00", joined)

    def test_layout_order_changes_output(self):
        blocks = [ReceiptBlock("A", "firm_name", TextStyle()), ReceiptBlock("B", "sector", TextStyle())]
        styles = {"firm_name": TextStyle(order=2), "sector": TextStyle(order=1)}
        self.assertEqual(apply_styles(blocks, styles, 32).plain_text(), "B\nA")

    def test_row_grouping_with_same_line(self):
        blocks = [ReceiptBlock("EKU: 001  ", "eku_label", TextStyle()), ReceiptBlock("Z: 707", "z_value", TextStyle())]
        styles = {"eku_label": TextStyle(same_line=True), "z_value": TextStyle()}
        self.assertEqual(apply_styles(blocks, styles, 32).plain_text(), "EKU: 001  Z: 707")

    def test_large_money_is_never_clipped(self):
        value = fit_styled_text("TOPKDV *12.345.678,90", TextStyle(width_scale=2), 32)
        self.assertIn("*12.345.678,90", value)

    def test_offset_undo_uses_full_snapshot(self):
        from receipt_styles import StyleUndoManager
        manager = StyleUndoManager({})
        manager.push({"vat_amount": {"x_offset": 7}})
        self.assertEqual(manager.undo(), {})
        self.assertEqual(manager.redo()["vat_amount"]["x_offset"], 7)

    def test_version_one_profile_migrates_without_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "styles.json"
            payload = {"version": 1, "firms": {"A": {"vat": {"bold": True}}}}
            path.write_text(json.dumps(payload), encoding="utf-8")
            store = FirmReceiptStyleStore(path)
            store.load()
            self.assertEqual(store.get("A"), payload["firms"]["A"])
            self.assertTrue(path.with_suffix(".json.v1.bak").exists())

    def test_field_and_full_reset_are_sparse_dictionary_operations(self):
        state = {"firm_name": {"bold": True}, "vat_amount": {"width_scale": 2}}
        state.pop("vat_amount")
        self.assertEqual(state, {"firm_name": {"bold": True}})
        state.clear()
        self.assertEqual(state, {})


if __name__ == "__main__":
    unittest.main()
