from __future__ import annotations

from pathlib import Path
from typing import List

try:
    import win32print
except ImportError:
    win32print = None

NF_LOGO_WIDTH = 160
NF_LOGO_HEIGHT = 24


def _new_canvas(width: int, height: int) -> list[list[int]]:
    return [[0 for _ in range(width)] for _ in range(height)]


def _set_pixel(pixels: list[list[int]], x: int, y: int) -> None:
    if 0 <= y < len(pixels) and 0 <= x < len(pixels[0]):
        pixels[y][x] = 1


def _thick_line(pixels: list[list[int]], x0: int, y0: int, x1: int, y1: int, thickness: int = 1) -> None:
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
    # Restore the known-good embedded NF bitmap mark. The surrounding whitespace is intentional;
    # it keeps the small logo visually close to the reference receipt when centered with the code.
    _thick_line(pixels, 42, 20, 50, 4, 1)
    _thick_line(pixels, 50, 4, 66, 20, 1)
    _thick_line(pixels, 66, 20, 74, 4, 1)
    _thick_line(pixels, 76, 20, 84, 4, 1)
    _thick_line(pixels, 84, 4, 107, 4, 1)
    _thick_line(pixels, 80, 12, 99, 12, 1)
    _thick_line(pixels, 38, 21, 56, 21, 1)
    _thick_line(pixels, 75, 21, 92, 21, 1)
    return pixels


def _pack_esc_star_24dot(pixels: list[list[int]]) -> bytes:
    height = len(pixels)
    width = len(pixels[0])
    if height > 24:
        raise ValueError("ESC * 24-dot logo height must be 24 pixels or less")
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
    return b"\x1b*\x21" + bytes([n_l, n_h]) + bytes(data)


NF_LOGO_ESC_STAR = _pack_esc_star_24dot(_build_logo_pixels())


class PrinterService:
    def list_printers(self) -> List[str]:
        if win32print is None:
            return []
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        return [p[2] for p in printers]

    def printer_exists(self, printer_name: str) -> bool:
        return printer_name.strip() in self.list_printers()

    def print_raw(self, printer_name: str, content: str, _logo_path: str | Path | None = None) -> None:
        if win32print is None:
            raise RuntimeError("pywin32 yüklü değil.")
        if not self.printer_exists(printer_name):
            raise RuntimeError("Yazıcı bulunamadı veya bağlı değil.")

        h_printer = win32print.OpenPrinter(printer_name)
        try:
            job = win32print.StartDocPrinter(h_printer, 1, ("Oyun Fişi", None, "RAW"))
            try:
                win32print.StartPagePrinter(h_printer)
                self._write_receipt_with_optional_logo(h_printer, content)
                win32print.WritePrinter(h_printer, b"\n\n\n\x1dV\x00")
                win32print.EndPagePrinter(h_printer)
            finally:
                win32print.EndDocPrinter(h_printer)
        finally:
            win32print.ClosePrinter(h_printer)

    def _write_receipt_with_optional_logo(self, h_printer, content: str) -> None:
        lines = content.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if stripped.startswith("[NF LOGO]"):
                footer_logo_code = stripped.removeprefix("[NF LOGO]").strip()
                if not footer_logo_code and index + 1 < len(lines):
                    next_line = lines[index + 1].strip()
                    if next_line:
                        footer_logo_code = next_line
                        index += 1
                if not self.print_bitmap_logo(h_printer, footer_logo_code):
                    print("NF bitmap fallback used")
                    fallback = " ".join(part for part in ["NF", footer_logo_code] if part)
                    win32print.WritePrinter(h_printer, f"{fallback}\n".encode("cp857", errors="replace"))
                index += 1
                continue
            win32print.WritePrinter(h_printer, f"{line}\n".encode("cp857", errors="replace"))
            index += 1

    def print_bitmap_logo(self, h_printer, footer_logo_code: str = "") -> bool:
        """Print the embedded NF bitmap, then the firm code as normal ESC/POS text on the same line."""
        if not NF_LOGO_ESC_STAR:
            return False

        code = footer_logo_code.strip().upper()
        win32print.WritePrinter(h_printer, b"\x1ba\x01")
        win32print.WritePrinter(h_printer, NF_LOGO_ESC_STAR)
        if code:
            win32print.WritePrinter(h_printer, f" {code}".encode("cp857", errors="replace"))
        win32print.WritePrinter(h_printer, b"\n\x1ba\x00")
        print("NF bitmap logo printed")
        return True

    def save_txt(self, output_dir: Path, filename: str, content: str) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        return path
