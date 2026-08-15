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

        # Boyutlar doğrudan bitmap matrisinden gelmeli.
        self.assertEqual(
            NF_LOGO_WIDTH,
            len(NF_LOGO_BITMAP[0]),
        )

        self.assertEqual(
            NF_LOGO_HEIGHT,
            len(NF_LOGO_BITMAP),
        )

        # Yeni kompakt logo eski 64x22 sürümden
        # kesinlikle daha küçük kalmalı.
        self.assertLess(
            NF_LOGO_WIDTH,
            64,
        )

        self.assertLess(
            NF_LOGO_HEIGHT,
            22,
        )

        # ESC * 24-dot sınırı.
        self.assertLessEqual(
            NF_LOGO_HEIGHT,
            24,
        )

        # Üretilen piksel matrisinin boyutları
        # kaynak bitmap ile tamamen eşleşmeli.
        self.assertEqual(
            len(pixels),
            NF_LOGO_HEIGHT,
        )

        self.assertTrue(
            all(
                len(row) == NF_LOGO_WIDTH
                for row in pixels
            )
        )

        # Kaynak bitmap sadece siyah/beyaz
        # piksel karakterlerinden oluşmalı.
        self.assertTrue(
            all(
                set(row) <= {".", "#"}
                for row in NF_LOGO_BITMAP
            )
        )

        # Logo boş olmamalı.
        self.assertGreater(
            sum(map(sum, pixels)),
            0,
        )

        # Raster çıktı düz ASCII NF olmamalı.
        self.assertNotEqual(
            NF_LOGO_ESC_STAR,
            b"NF",
        )

        # ---------------------------------------------------------
        # NATURAL BOUNDING BOX KONTROLÜ
        # ---------------------------------------------------------
        #
        # Bitmap çevresinde tamamen boş padding bırakılmamalı.
        # İlk/son satır ve ilk/son sütunda en az bir siyah
        # piksel bulunmalı.
        #
        # Böylece width/height gerçek logoyu temsil eder.
        self.assertTrue(
            any(pixels[0])
        )

        self.assertTrue(
            any(pixels[-1])
        )

        self.assertTrue(
            any(
                row[0]
                for row in pixels
            )
        )

        self.assertTrue(
            any(
                row[-1]
                for row in pixels
            )
        )

        # ---------------------------------------------------------
        # N HARFİNİN KRİTİK SON DİYAGONALİ
        # ---------------------------------------------------------
        #
        # Son fiziksel baskı karşılaştırmasına göre N'nin
        # orta-alt çukuru x=22 civarında,
        # F ile birleştiği üst nokta x=30 civarında.
        #
        # Böylece son yükselen diyagonal:
        #
        # 30 - 22 = 8 px
        #
        # Eski yaklaşık 13 px genişliğindeki sürümden
        # belirgin şekilde daha kısa.
        self.assertTrue(
            pixels[13][22]
        )

        self.assertTrue(
            pixels[4][30]
        )

        self.assertLess(
            30 - 22,
            13,
        )

        # ---------------------------------------------------------
        # F ALT KOL KONTROLÜ
        # ---------------------------------------------------------
        #
        # F'nin orta kolunun altında sağ tarafa uzayan
        # yatay bir alt kol bulunmamalı.
        #
        # Böylece F hiçbir zaman E gibi görünmez.
        for row in pixels[10:]:
            self.assertFalse(
                any(row[31:])
            )

        # ---------------------------------------------------------
        # İNCE DİYAGONAL BAĞLANTI KONTROLÜ
        # ---------------------------------------------------------
        #
        # Ardışık dolu satırlar en az bir ortak sütun
        # paylaşmalı.
        #
        # 2+ piksel overlap zorlamıyoruz; çünkü bu,
        # ince referans logoyu gereksiz kalınlaştırabilir.
        occupied_rows = [
            {
                x
                for x, value in enumerate(row)
                if value
            }
            for row in pixels
        ]

        for upper, lower in zip(
            occupied_rows,
            occupied_rows[1:],
        ):
            if upper and lower:
                self.assertGreaterEqual(
                    len(upper & lower),
                    1,
                )

    def test_nf_logo_placeholder_is_replaced_before_cp857_text_write(self):
        fake_win32print = FakeWin32Print()
        service = PrinterService()

        with patch.object(
            printer_module,
            "win32print",
            fake_win32print,
        ), patch.object(
            service,
            "print_bitmap_logo",
            wraps=service.print_bitmap_logo,
        ) as print_bitmap_logo:

            service.print_raw(
                "TEST_PRINTER",
                "UST\n   [NF LOGO]  JH 20018559",
            )

        print_bitmap_logo.assert_called_once_with(
            "TEST_PRINTER",
            "JH 20018559",
        )

        written = b"".join(
            fake_win32print.writes
        )

        # Placeholder gerçek RAW çıktıya gitmemeli.
        self.assertNotIn(
            b"[NF LOGO]",
            written,
        )

        # Firma kodu bitmap'in içine rasterlaştırılmamalı.
        # Normal CP857 text olarak kalmalı.
        self.assertIn(
            b" JH 20018559",
            written,
        )

        self.assertIn(
            "JH 20018559".encode("cp857"),
            written,
        )

        # Stilize Unicode NF karakterleri yanlışlıkla
        # RAW çıktıya UTF-8 olarak gönderilmemeli.
        self.assertNotIn(
            bytes.fromhex("f09d9895"),
            written,
        )

        self.assertNotIn(
            bytes.fromhex("f09d988d"),
            written,
        )

        # ESC/POS ESC * 24-dot bitmap komutu
        # gerçekten yazıcıya gönderilmeli.
        self.assertTrue(
            any(
                chunk.startswith(b"\x1b*\x21")
                for chunk in fake_win32print.writes
            )
        )

    def test_nf_logo_fallback_uses_plain_ascii_nf(self):
        fake_win32print = FakeWin32Print()
        service = PrinterService()

        with patch.object(
            printer_module,
            "win32print",
            fake_win32print,
        ), patch.object(
            service,
            "print_bitmap_logo",
            return_value=False,
        ) as print_bitmap_logo:

            service.print_raw(
                "TEST_PRINTER",
                "[NF LOGO]  JH 20018559",
            )

        print_bitmap_logo.assert_called_once_with(
            "TEST_PRINTER",
            "JH 20018559",
        )

        written = b"".join(
            fake_win32print.writes
        )

        # Bitmap başarısız olursa güvenli
        # ASCII NF fallback kullanılmalı.
        self.assertIn(
            b"NF JH 20018559\n",
            written,
        )

        # Placeholder hiçbir koşulda
        # yazıcıya ulaşmamalı.
        self.assertNotIn(
            b"[NF LOGO]",
            written,
        )


if __name__ == "__main__":
    unittest.main()