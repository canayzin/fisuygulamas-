from __future__ import annotations

from pathlib import Path
from typing import List

try:
    import win32print
except ImportError:
    win32print = None

NF_LOGO_WIDTH = 160
NF_LOGO_HEIGHT = 24


def _build_embedded_nf_logo_raster() -> bytes:
    pixels = [[0 for _ in range(NF_LOGO_WIDTH)] for _ in range(NF_LOGO_HEIGHT)]

    def set_pixel(x: int, y: int) -> None:
        if 0 <= x < NF_LOGO_WIDTH and 0 <= y < NF_LOGO_HEIGHT:
            pixels[y][x] = 1

    def thick_line(x0: int, y0: int, x1: int, y1: int, thickness: int = 1) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        while True:
            for ox in range(-thickness, thickness + 1):
                for oy in range(-thickness, thickness + 1):
                    set_pixel(x + ox, y + oy)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    # Slanted NF mark centered inside a 160x24 monochrome raster.
    thick_line(42, 20, 50, 4, 1)
    thick_line(50, 4, 66, 20, 1)
    thick_line(66, 20, 74, 4, 1)
    thick_line(76, 20, 84, 4, 1)
    thick_line(84, 4, 107, 4, 1)
    thick_line(80, 12, 99, 12, 1)
    thick_line(38, 21, 56, 21, 1)
    thick_line(75, 21, 92, 21, 1)

    width_bytes = (NF_LOGO_WIDTH + 7) // 8
    raster = bytearray()
    for y in range(NF_LOGO_HEIGHT):
        for byte_x in range(width_bytes):
            value = 0
            for bit in range(8):
                x = byte_x * 8 + bit
                if x < NF_LOGO_WIDTH and pixels[y][x]:
                    value |= 0x80 >> bit
            raster.append(value)
    return bytes(raster)


NF_LOGO_RASTER = _build_embedded_nf_logo_raster()


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
        for line in content.splitlines():
            if line.strip() == "[NF LOGO]":
                if not self.print_bitmap_logo(h_printer):
                    win32print.WritePrinter(h_printer, b"NF\n")
                continue
            win32print.WritePrinter(h_printer, f"{line}\n".encode("cp857", errors="replace"))

    def print_bitmap_logo(self, h_printer) -> bool:
        """Print the embedded 1-bit NF bitmap with the ESC/POS GS v 0 raster command."""
        if not NF_LOGO_RASTER:
            return False

        width_bytes = (NF_LOGO_WIDTH + 7) // 8
        x_l = width_bytes & 0xFF
        x_h = (width_bytes >> 8) & 0xFF
        y_l = NF_LOGO_HEIGHT & 0xFF
        y_h = (NF_LOGO_HEIGHT >> 8) & 0xFF
        command = b"\x1dv0\x00" + bytes([x_l, x_h, y_l, y_h]) + NF_LOGO_RASTER

        win32print.WritePrinter(h_printer, b"\x1ba\x01")
        win32print.WritePrinter(h_printer, command)
        win32print.WritePrinter(h_printer, b"\n\x1ba\x00")
        return True

    def save_txt(self, output_dir: Path, filename: str, content: str) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        return path
