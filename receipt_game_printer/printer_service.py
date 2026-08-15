from __future__ import annotations

from pathlib import Path
from typing import List

try:
    import win32print
except ImportError:
    win32print = None


# ---------------------------------------------------------------------------
# NF LOGO
#
# Sabit, elle ayarlanmış 1-bit bitmap.
#
# "#" = siyah termal piksel
# "." = boş piksel
#
# Font, Unicode, Pillow, PNG veya koordinat tabanlı çizgi üretimi kullanılmaz.
# ---------------------------------------------------------------------------

NF_LOGO_BITMAP = (
    "....................................................................",
    "...............###..................................................",
    "..............#####....................#############################",
    "..............######...................#############################",
    ".............#######..................##############################",
    "............#########.................#####.........................",
    "...........#####.#####...............#####..........................",
    "...........####...#####.............######..........................",
    "..........####.....#####...........#######..........................",
    ".........#####......#####.........##########################........",
    "........#####........####.........##########################........",
    "........####..........####.......###########################........",
    ".......####...........#####.....########............................",
    "......#####............#####...#####.###............................",
    ".....#####..............#####.#####.####............................",
    ".....####................####.####..####............................",
    "....####..................#######...###.............................",
    "...#####..................#######..####.............................",
    "..#####....................#####...####.............................",
    "..####......................###....###..............................",
    ".####.............................####..............................",
    ".####.............................####..............................",
    ".###..............................###...............................",
    "..................................###...............................",
)

NF_LOGO_HEIGHT = len(NF_LOGO_BITMAP)
NF_LOGO_WIDTH = len(NF_LOGO_BITMAP[0])


def _build_logo_pixels() -> list[list[int]]:
    """
    Sabit NF bitmap'ini 1-bit piksel matrisine dönüştür.

    Font, Unicode, Pillow veya geometrik çizgi üretimi kullanılmaz.
    """

    if not NF_LOGO_BITMAP:
        raise ValueError("NF logo bitmap is empty")

    if NF_LOGO_WIDTH <= 0:
        raise ValueError("NF logo bitmap width must be greater than zero")

    if NF_LOGO_HEIGHT > 24:
        raise ValueError(
            "NF logo bitmap height must be 24 pixels or less"
        )

    if any(
        len(row) != NF_LOGO_WIDTH
        for row in NF_LOGO_BITMAP
    ):
        raise ValueError(
            "NF logo bitmap rows must have equal width"
        )

    invalid_pixels = {
        pixel
        for row in NF_LOGO_BITMAP
        for pixel in row
        if pixel not in {"#", "."}
    }

    if invalid_pixels:
        raise ValueError(
            "NF logo bitmap may contain only '#' and '.'"
        )

    return [
        [
            1 if pixel == "#" else 0
            for pixel in row
        ]
        for row in NF_LOGO_BITMAP
    ]


def _pack_esc_star_24dot(
    pixels: list[list[int]],
) -> bytes:
    """
    1-bit bitmap'i ESC/POS ESC * 24-dot formatına dönüştür.
    """

    if not pixels:
        raise ValueError(
            "Logo pixel matrix is empty"
        )

    if not pixels[0]:
        raise ValueError(
            "Logo pixel matrix width is zero"
        )

    height = len(pixels)
    width = len(pixels[0])

    if height > 24:
        raise ValueError(
            "ESC * 24-dot logo height must be 24 pixels or less"
        )

    if any(
        len(row) != width
        for row in pixels
    ):
        raise ValueError(
            "Logo pixel rows must have equal width"
        )

    data = bytearray()

    # ESC * 24-dot veri yapısı sütun bazlıdır.
    # Her sütun için 3 byte = 24 dikey piksel.
    for x in range(width):
        for block in range(3):
            value = 0

            for bit in range(8):
                y = block * 8 + bit

                if (
                    y < height
                    and pixels[y][x]
                ):
                    value |= 0x80 >> bit

            data.append(value)

    n_l = width & 0xFF
    n_h = (width >> 8) & 0xFF

    return (
        b"\x1b*\x21"
        + bytes([n_l, n_h])
        + bytes(data)
    )


NF_LOGO_ESC_STAR = _pack_esc_star_24dot(
    _build_logo_pixels()
)


class PrinterService:
    def list_printers(self) -> List[str]:
        if win32print is None:
            return []

        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL
            | win32print.PRINTER_ENUM_CONNECTIONS
        )

        return [
            printer[2]
            for printer in printers
        ]

    def printer_exists(
        self,
        printer_name: str,
    ) -> bool:
        return (
            printer_name.strip()
            in self.list_printers()
        )

    def print_raw(
        self,
        printer_name: str,
        content: str,
        _logo_path: str | Path | None = None,
    ) -> None:
        if win32print is None:
            raise RuntimeError(
                "pywin32 yüklü değil."
            )

        if not self.printer_exists(
            printer_name
        ):
            raise RuntimeError(
                "Yazıcı bulunamadı veya bağlı değil."
            )

        h_printer = win32print.OpenPrinter(
            printer_name
        )

        try:
            win32print.StartDocPrinter(
                h_printer,
                1,
                (
                    "Oyun Fişi",
                    None,
                    "RAW",
                ),
            )

            try:
                win32print.StartPagePrinter(
                    h_printer
                )

                self._write_receipt_with_optional_logo(
                    h_printer,
                    content,
                )

                # Birkaç boş satır + kesme komutu.
                win32print.WritePrinter(
                    h_printer,
                    b"\n\n\n\x1dV\x00",
                )

                win32print.EndPagePrinter(
                    h_printer
                )

            finally:
                win32print.EndDocPrinter(
                    h_printer
                )

        finally:
            win32print.ClosePrinter(
                h_printer
            )

    def _write_receipt_with_optional_logo(
        self,
        h_printer,
        content: str,
    ) -> None:
        """
        [NF LOGO] placeholder'ını metne çevrilmeden önce yakala.

        Placeholder hiçbir zaman CP857 metni olarak yazıcıya gitmez.
        """

        lines = content.splitlines()
        index = 0

        while index < len(lines):
            line = lines[index]
            stripped = line.strip()

            if stripped.startswith("[NF LOGO]"):
                footer_logo_code = (
                    stripped
                    .removeprefix("[NF LOGO]")
                    .strip()
                )

                # Eski formatlarda firma kodu bir sonraki
                # satırda bulunabiliyor.
                if (
                    not footer_logo_code
                    and index + 1 < len(lines)
                ):
                    next_line = (
                        lines[index + 1]
                        .strip()
                    )

                    if next_line:
                        footer_logo_code = (
                            next_line
                        )
                        index += 1

                if not self.print_bitmap_logo(
                    h_printer,
                    footer_logo_code,
                ):
                    print(
                        "NF bitmap fallback used"
                    )

                    fallback = " ".join(
                        part
                        for part in (
                            "NF",
                            footer_logo_code,
                        )
                        if part
                    )

                    win32print.WritePrinter(
                        h_printer,
                        f"{fallback}\n".encode(
                            "cp857",
                            errors="replace",
                        ),
                    )

                index += 1
                continue

            win32print.WritePrinter(
                h_printer,
                f"{line}\n".encode(
                    "cp857",
                    errors="replace",
                ),
            )

            index += 1

    def print_bitmap_logo(
        self,
        h_printer,
        footer_logo_code: str = "",
    ) -> bool:
        """
        NF bitmap logosunu RAW olarak bas.

        Firma kodu rasterlaştırılmaz; logodan sonra normal CP857
        metni olarak gönderilir.
        """

        if not NF_LOGO_ESC_STAR:
            return False

        code = (
            footer_logo_code
            .strip()
            .upper()
        )

        try:
            # Ortala.
            win32print.WritePrinter(
                h_printer,
                b"\x1ba\x01",
            )

            # NF bitmap.
            win32print.WritePrinter(
                h_printer,
                NF_LOGO_ESC_STAR,
            )

            # Firma kodu normal text.
            if code:
                win32print.WritePrinter(
                    h_printer,
                    f" {code}".encode(
                        "cp857",
                        errors="replace",
                    ),
                )

            # Satırı bitir ve tekrar sola hizala.
            win32print.WritePrinter(
                h_printer,
                b"\n\x1ba\x00",
            )

        except Exception:
            # Bitmap basılamazsa üst fonksiyon ASCII NF fallback
            # kullanacak.
            return False

        print(
            "NF bitmap logo printed"
        )

        return True

    def save_txt(
        self,
        output_dir: Path,
        filename: str,
        content: str,
    ) -> Path:
        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = (
            output_dir
            / filename
        )

        path.write_text(
            content,
            encoding="utf-8",
        )

        return path