from __future__ import annotations

from pathlib import Path
from typing import List

try:
    import win32print
except ImportError:
    win32print = None

NF_LOGO_WIDTH = 58
NF_LOGO_HEIGHT = 18
NF_CODE_SCALE = 2
NF_LOGO_CODE_GAP = 10

_DIGIT_FONT = {
    "0": ("111", "101", "101", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "010", "010", "111"),
    "2": ("111", "001", "001", "111", "100", "100", "111"),
    "3": ("111", "001", "001", "111", "001", "001", "111"),
    "4": ("101", "101", "101", "111", "001", "001", "001"),
    "5": ("111", "100", "100", "111", "001", "001", "111"),
    "6": ("111", "100", "100", "111", "101", "101", "111"),
    "7": ("111", "001", "001", "010", "010", "010", "010"),
    "8": ("111", "101", "101", "111", "101", "101", "111"),
    "9": ("111", "101", "101", "111", "001", "001", "111"),
}

_LETTER_FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("111", "010", "010", "010", "010", "010", "111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
}


def _new_canvas(width: int, height: int) -> list[list[int]]:
    return [[0 for _ in range(width)] for _ in range(height)]


def _set_pixel(pixels: list[list[int]], x: int, y: int) -> None:
    if 0 <= y < len(pixels) and 0 <= x < len(pixels[0]):
        pixels[y][x] = 1


def _line(pixels: list[list[int]], x0: int, y0: int, x1: int, y1: int) -> None:
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        _set_pixel(pixels, x, y)
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


def _draw_nf_logo(pixels: list[list[int]], x_offset: int, y_offset: int) -> None:
    # Thin, low-profile slanted NF mark. The F has only top/middle arms to avoid an E-like shape.
    _line(pixels, x_offset + 3, y_offset + 15, x_offset + 9, y_offset + 2)
    _line(pixels, x_offset + 9, y_offset + 2, x_offset + 24, y_offset + 15)
    _line(pixels, x_offset + 24, y_offset + 15, x_offset + 30, y_offset + 2)
    _line(pixels, x_offset + 36, y_offset + 15, x_offset + 42, y_offset + 2)
    _line(pixels, x_offset + 42, y_offset + 2, x_offset + 56, y_offset + 2)
    _line(pixels, x_offset + 39, y_offset + 8, x_offset + 52, y_offset + 8)


def _glyph_for(char: str) -> tuple[str, ...]:
    if char == " ":
        return ("0",) * 7
    return _DIGIT_FONT.get(char) or _LETTER_FONT.get(char.upper()) or _LETTER_FONT["X"]


def _text_width(text: str, scale: int = NF_CODE_SCALE) -> int:
    width = 0
    for char in text:
        glyph = _glyph_for(char)
        width += len(glyph[0]) * scale + scale
    return max(width - scale, 0)


def _draw_text(pixels: list[list[int]], text: str, x_offset: int, y_offset: int, scale: int = NF_CODE_SCALE) -> None:
    cursor = x_offset
    for char in text:
        glyph = _glyph_for(char)
        for row_index, row in enumerate(glyph):
            for col_index, bit in enumerate(row):
                if bit != "1":
                    continue
                for y_scale in range(scale):
                    for x_scale in range(scale):
                        _set_pixel(pixels, cursor + col_index * scale + x_scale, y_offset + row_index * scale + y_scale)
        cursor += len(glyph[0]) * scale + scale


def _pack_raster(pixels: list[list[int]]) -> bytes:
    height = len(pixels)
    width = len(pixels[0])
    width_bytes = (width + 7) // 8
    raster = bytearray()
    for y in range(height):
        for byte_x in range(width_bytes):
            value = 0
            for bit in range(8):
                x = byte_x * 8 + bit
                if x < width and pixels[y][x]:
                    value |= 0x80 >> bit
            raster.append(value)
    return bytes(raster)


def _build_logo_raster(footer_logo_code: str = "") -> tuple[int, int, bytes]:
    code = footer_logo_code.strip().upper()
    code_width = _text_width(code) if code else 0
    width = NF_LOGO_WIDTH + (NF_LOGO_CODE_GAP + code_width if code else 0)
    height = NF_LOGO_HEIGHT
    pixels = _new_canvas(width, height)
    _draw_nf_logo(pixels, 0, 1)
    if code:
        _draw_text(pixels, code, NF_LOGO_WIDTH + NF_LOGO_CODE_GAP, 3)
    return width, height, _pack_raster(pixels)


NF_LOGO_RASTER = _build_logo_raster()[2]


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
                    fallback = "  ".join(part for part in ["NF", footer_logo_code] if part)
                    win32print.WritePrinter(h_printer, f"{fallback}\n".encode("cp857", errors="replace"))
                index += 1
                continue
            win32print.WritePrinter(h_printer, f"{line}\n".encode("cp857", errors="replace"))
            index += 1

    def print_bitmap_logo(self, h_printer, footer_logo_code: str = "") -> bool:
        """Print the embedded 1-bit NF bitmap and optional code as one centered raster line."""
        width, height, raster = _build_logo_raster(footer_logo_code)
        if not raster:
            return False

        width_bytes = (width + 7) // 8
        x_l = width_bytes & 0xFF
        x_h = (width_bytes >> 8) & 0xFF
        y_l = height & 0xFF
        y_h = (height >> 8) & 0xFF
        command = b"\x1dv0\x00" + bytes([x_l, x_h, y_l, y_h]) + raster

        win32print.WritePrinter(h_printer, b"\x1ba\x01")
        win32print.WritePrinter(h_printer, command)
        win32print.WritePrinter(h_printer, b"\n\x1ba\x00")
        print("NF bitmap logo printed")
        return True

    def save_txt(self, output_dir: Path, filename: str, content: str) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        return path
