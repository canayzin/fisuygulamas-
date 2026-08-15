from __future__ import annotations

from pathlib import Path
from typing import List

try:
    import win32print
except ImportError:
    win32print = None


NF_LOGO_WIDTH = 58
NF_LOGO_HEIGHT = 18


def _new_canvas(width: int, height: int) -> list[list[int]]:
    return [[0 for _ in range(width)] for _ in range(height)]


def _set_pixel(pixels: list[list[int]], x: int, y: int) -> None:
    if 0 <= y < len(pixels) and 0 <= x < len(pixels[0]):
        pixels[y][x] = 1


def _thick_line(
    pixels: list[list[int]],
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    thickness: int = 1,
) -> None:
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0

    while True:
        for ox in range(-thickness, thickness + 1):
            for oy in range(-thickness, thickness + 1):
                _set_pixel(pixels, x + ox, y + oy)

        if x == x1 and y == y1:
            break

        e2 = 2 * err

        if e2 >= dy:
            err += dy
            x += sx

        if e2 <= dx:
            err += dx
            y += sy


def _build_logo_pixels() -> list[list[int]]:
    pixels = _new_canvas(NF_LOGO_WIDTH, NF_LOGO_HEIGHT)

    # Compact, single-stroke italic NF monogram.
    #
    # N'nin sağ yükselen çizgisi aynı zamanda F'nin başlangıç gövdesi
    # olarak kullanılır. Böylece iki ayrı normal "N" ve "F" karakteri
    # yerine referans fişteki gibi bağlantılı tek bir sembol elde edilir.
    #
    # thickness=0 kullanılması bilinçlidir:
    # _thick_line fonksiyonunda bu değer gerçek 1 piksel çizgi üretir.
    # Böylece logo gereksiz şekilde bold görünmez.

    # N: kısa sol yükselen stroke.
    _thick_line(
        pixels,
        2,
        15,
        7,
        2,
        thickness=0,
    )

    # N: aşağı inen ana diagonal.
    _thick_line(
        pixels,
        7,
        2,
        20,
        15,
        thickness=0,
    )

    # N'nin sağ yükselen çizgisi / F ile paylaşılan bağlantı.
    _thick_line(
        pixels,
        20,
        15,
        27,
        2,
        thickness=0,
    )

    # F: üst kol.
    _thick_line(
        pixels,
        27,
        2,
        55,
        2,
        thickness=0,
    )

    # F: orta kol.
    # Bilerek alt kol eklenmez; böylece F, E harfine dönüşmez.
    _thick_line(
        pixels,
        24,
        8,
        46,
        8,
        thickness=0,
    )

    return pixels


def _pack_esc_star_24dot(pixels: list[list[int]]) -> bytes:
    height = len(pixels)
    width = len(pixels[0])

    if height > 24:
        raise ValueError(
            "ESC * 24-dot logo height must be 24 pixels or less"
        )

    data = bytearray()

    for x in range(width):
        for block in range(3):
            value = 0

            for bit in range(8):
                y = block * 8 + bit

                if y < height and pixels[y][x]:
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

        return [p[2] for p in printers]

    def printer_exists(self, printer_name: str) -> bool:
        return printer_name.strip() in self.list_printers()

    def print_raw(
        self,
        printer_name: str,
        content: str,
        _logo_path: str | Path | None = None,
    ) -> None:
        if win32print is None:
            raise RuntimeError("pywin32 yüklü değil.")

        if not self.printer_exists(printer_name):
            raise RuntimeError(
                "Yazıcı bulunamadı veya bağlı değil."
            )

        h_printer = win32print.OpenPrinter(printer_name)

        try:
            win32print.StartDocPrinter(
                h_printer,
                1,
                ("Oyun Fişi", None, "RAW"),
            )

            try:
                win32print.StartPagePrinter(h_printer)

                self._write_receipt_with_optional_logo(
                    h_printer,
                    content,
                )

                win32print.WritePrinter(
                    h_printer,
                    b"\n\n\n\x1dV\x00",
                )

                win32print.EndPagePrinter(h_printer)

            finally:
                win32print.EndDocPrinter(h_printer)

        finally:
            win32print.ClosePrinter(h_printer)

    def _write_receipt_with_optional_logo(
        self,
        h_printer,
        content: str,
    ) -> None:
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

                # Eski formatlarda kod bir sonraki satırda
                # tutuluyor olabilir. Bu desteği koruyoruz.
                if (
                    not footer_logo_code
                    and index + 1 < len(lines)
                ):
                    next_line = lines[index + 1].strip()

                    if next_line:
                        footer_logo_code = next_line
                        index += 1

                if not self.print_bitmap_logo(
                    h_printer,
                    footer_logo_code,
                ):
                    print("NF bitmap fallback used")

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
        Print the embedded NF bitmap and then print the firm
        code as ordinary CP857 text.

        The NF mark is never encoded as Unicode/text.
        """
        if not NF_LOGO_ESC_STAR:
            return False

        code = footer_logo_code.strip().upper()

        # Center alignment.
        win32print.WritePrinter(
            h_printer,
            b"\x1ba\x01",
        )

        # Embedded NF raster/ESC-* data.
        win32print.WritePrinter(
            h_printer,
            NF_LOGO_ESC_STAR,
        )

        # Firma kodu raster yapılmaz; normal CP857 text kalır.
        if code:
            win32print.WritePrinter(
                h_printer,
                f" {code}".encode(
                    "cp857",
                    errors="replace",
                ),
            )

        # Yeni satır + tekrar sol hizalama.
        win32print.WritePrinter(
            h_printer,
            b"\n\x1ba\x00",
        )

        print("NF bitmap logo printed")
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

        path = output_dir / filename

        path.write_text(
            content,
            encoding="utf-8",
        )

        return path