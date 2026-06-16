from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import printer_service as printer_module
from printer_service import PrinterService


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
    def test_nf_logo_placeholder_is_replaced_before_cp857_text_write(self):
        fake_win32print = FakeWin32Print()
        service = PrinterService()

        with patch.object(printer_module, "win32print", fake_win32print), patch.object(
            service, "print_bitmap_logo", wraps=service.print_bitmap_logo
        ) as print_bitmap_logo:
            service.print_raw("TEST_PRINTER", "UST\n   [NF LOGO]   \nJH 20018559")

        print_bitmap_logo.assert_called_once_with("TEST_PRINTER")
        written = b"".join(fake_win32print.writes)
        self.assertNotIn(b"[NF LOGO]", written)
        self.assertIn(b"JH 20018559\n", written)
        self.assertNotIn(bytes.fromhex("f09d9895"), written)
        self.assertNotIn(bytes.fromhex("f09d988d"), written)
        self.assertTrue(any(chunk.startswith(b"\x1dv0\x00") for chunk in fake_win32print.writes))

    def test_nf_logo_fallback_uses_plain_ascii_nf(self):
        fake_win32print = FakeWin32Print()
        service = PrinterService()

        with patch.object(printer_module, "win32print", fake_win32print), patch.object(
            service, "print_bitmap_logo", return_value=False
        ) as print_bitmap_logo:
            service.print_raw("TEST_PRINTER", "[NF LOGO]")

        print_bitmap_logo.assert_called_once_with("TEST_PRINTER")
        written = b"".join(fake_win32print.writes)
        self.assertIn(b"NF\n", written)
        self.assertNotIn(b"[NF LOGO]", written)


if __name__ == "__main__":
    unittest.main()
