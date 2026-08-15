from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import printer_service as printer_module
from printer_service import (
    NF_LOGO_BITMAP,
    NF_LOGO_ESC_STAR,
    NF_LOGO_HEIGHT,
    NF_LOGO_WIDTH,
    PrinterService,
    _build_logo_pixels,
)


class FakeWin32Print:
    PRINTER_ENUM_LOCAL = 1
    PRINTER_ENUM_CONNECTIONS = 2

    def __init__(self):
        self.writes: list[bytes] = []

    def EnumPrinters(self, _flags):
        return [(None, None, "TEST_PRINTER")]

    def OpenPrinter(self, printer_name):
        return printer_name

    def ClosePrinter(self, _handle):
        return None

    def StartDocPrinter(self, _handle, _level, _info):
        return 1

    def EndDocPrinter(self, _handle):
        return None

    def StartPagePrinter(self, _handle):
        return None

    def EndPagePrinter(self, _handle):
        return None

    def WritePrinter(self, _handle, data: bytes):
        self.writes.append(data)


class PrinterServiceLogoTests(unittest.TestCase):
    def test_nf_logo_is_a_small_nonempty_monogram_without_f_bottom_arm(self):
        pixels = _build_logo_pixels()

        self.assertEqual(NF_LOGO_WIDTH, len(NF_LOGO_BITMAP[0]))
        self.assertEqual(NF_LOGO_HEIGHT, len(NF_LOGO_BITMAP))
        self.assertGreaterEqual(NF_LOGO_WIDTH, 60)
        self.assertLessEqual(NF_LOGO_WIDTH, 72)
        self.assertGreaterEqual(NF_LOGO_HEIGHT, 22)
        self.assertLessEqual(NF_LOGO_HEIGHT, 24)
        self.assertEqual(len(pixels), NF_LOGO_HEIGHT)
        self.assertTrue(all(len(row) == NF_LOGO_WIDTH for row in pixels))
        self.assertTrue(all(set(row) <= {".", "#"} for row in NF_LOGO_BITMAP))
        black_pixel_count = sum(map(sum, pixels))
        self.assertGreater(black_pixel_count, NF_LOGO_WIDTH * NF_LOGO_HEIGHT * 0.15)
        self.assertNotEqual(NF_LOGO_ESC_STAR, b"NF")

        # Below the middle arm, the right side stays empty: the diagonal F
        # stem continues down-left without acquiring an E-like lower arm.
        for row in pixels[13:]:
            self.assertFalse(any(row[42:]))

        # Adjacent occupied rows must overlap by multiple pixels. This keeps
        # diagonal strokes dark and physically connected on a thermal head.
        occupied_rows = [{x for x, value in enumerate(row) if value} for row in pixels]
        for upper, lower in zip(occupied_rows, occupied_rows[1:]):
            if upper and lower:
                self.assertGreaterEqual(len(upper & lower), 2)

    def test_nf_logo_placeholder_is_replaced_before_cp857_text_write(self):
        fake_win32print = FakeWin32Print()
        service = PrinterService()

        with patch.object(printer_module, "win32print", fake_win32print), patch.object(
            service, "print_bitmap_logo", wraps=service.print_bitmap_logo
        ) as print_bitmap_logo:
            service.print_raw("TEST_PRINTER", "UST\n   [NF LOGO]  JH 20018559")

        print_bitmap_logo.assert_called_once_with("TEST_PRINTER", "JH 20018559")
        written = b"".join(fake_win32print.writes)
        self.assertNotIn(b"[NF LOGO]", written)
        self.assertIn(b" JH 20018559", written)
        self.assertIn("JH 20018559".encode("cp857"), written)
        self.assertNotIn(bytes.fromhex("f09d9895"), written)
        self.assertNotIn(bytes.fromhex("f09d988d"), written)
        self.assertTrue(any(chunk.startswith(b"\x1b*\x21") for chunk in fake_win32print.writes))

    def test_nf_logo_fallback_uses_plain_ascii_nf(self):
        fake_win32print = FakeWin32Print()
        service = PrinterService()

        with patch.object(printer_module, "win32print", fake_win32print), patch.object(
            service, "print_bitmap_logo", return_value=False
        ) as print_bitmap_logo:
            service.print_raw("TEST_PRINTER", "[NF LOGO]  JH 20018559")

        print_bitmap_logo.assert_called_once_with("TEST_PRINTER", "JH 20018559")
        written = b"".join(fake_win32print.writes)
        self.assertIn(b"NF JH 20018559\n", written)
        self.assertNotIn(b"[NF LOGO]", written)


if __name__ == "__main__":
    unittest.main()
