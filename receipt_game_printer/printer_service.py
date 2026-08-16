from __future__ import annotations

from pathlib import Path
from typing import List
from receipt_styles import StyledReceipt

try:
    import win32print
except ImportError:
    win32print = None

NF_LOGO_BITMAP = (
    ".........###..............#.################.",
    "........##.##............#.##................",
    ".......##...##..........#.##.................",
    "......##.....##........##.##.................",
    "......##......##......##.##..................",
    ".....##........##.....##.###############.....",
    "....##.........##....##.##...................",
    "...##...........##..##..##...................",
    "...##............####...##...................",
    "..##..............##....##...................",
    ".##....................##....................",
    ".##...................##.....................",
    "##...................##......................",
    "....................##.......................",
)
NF_LOGO_HEIGHT = len(NF_LOGO_BITMAP)
NF_LOGO_WIDTH = len(NF_LOGO_BITMAP[0])


def _build_logo_pixels(y_offset: int = 0) -> list[list[int]]:
    """Return the hand-tuned 1-bit monogram without font or line rendering."""
    if any(len(row) != NF_LOGO_WIDTH for row in NF_LOGO_BITMAP):
        raise ValueError("NF logo bitmap rows must have equal width")
    pixels = [[1 if pixel == "#" else 0 for pixel in row] for row in NF_LOGO_BITMAP]
    if not y_offset:
        return pixels
    canvas = [[0] * NF_LOGO_WIDTH for _ in range(24)]
    for y, row in enumerate(pixels):
        target = y + y_offset
        if 0 <= target < 24:
            canvas[target] = row[:]
    return canvas


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

    def print_raw(self, printer_name: str, content: str | StyledReceipt, _logo_path: str | Path | None = None) -> None:
        if win32print is None:
            raise RuntimeError("pywin32 yüklü değil.")
        if not self.printer_exists(printer_name):
            raise RuntimeError("Yazıcı bulunamadı veya bağlı değil.")

        h_printer = win32print.OpenPrinter(printer_name)
        try:
            job = win32print.StartDocPrinter(h_printer, 1, ("Oyun Fişi", None, "RAW"))
            try:
                win32print.StartPagePrinter(h_printer)
                if isinstance(content, StyledReceipt):
                    self._write_styled_receipt(h_printer, content)
                else:
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

    def _write_styled_receipt(self, h_printer, receipt: StyledReceipt) -> None:
        """Render shared receipt blocks as isolated ESC/POS style operations."""
        win32print.WritePrinter(h_printer, b"\x1b@")
        align_codes = {"left": 0, "center": 1, "right": 2}
        for block in receipt.blocks:
            stripped = block.text.strip()
            if stripped.startswith("[NF LOGO]"):
                code = stripped.removeprefix("[NF LOGO]").strip()
                if not self.print_bitmap_logo(h_printer, code, block.style.align, block.style):
                    fallback = " ".join(part for part in ["NF", code] if part)
                    win32print.WritePrinter(h_printer, f"{fallback}\n".encode("cp857", errors="replace"))
                self._write_style_reset(h_printer)
                continue
            size = ((block.style.width_scale - 1) << 4) | (block.style.height_scale - 1)
            win32print.WritePrinter(h_printer, b"\x1ba" + bytes([align_codes[block.style.align]]))
            win32print.WritePrinter(h_printer, b"\x1bE" + bytes([1 if block.style.bold else 0]))
            win32print.WritePrinter(h_printer, b"\x1d!" + bytes([size]))
            ending = "" if block.style.same_line else "\n"
            win32print.WritePrinter(h_printer, f"{block.text}{ending}".encode("cp857", errors="replace"))
            self._write_style_reset(h_printer)
        self._write_style_reset(h_printer)

    def _write_style_reset(self, h_printer) -> None:
        win32print.WritePrinter(h_printer, b"\x1bE\x00\x1d!\x00\x1ba\x00")

    def print_bitmap_logo(self, h_printer, footer_logo_code: str = "", align: str = "center", style=None) -> bool:
        """Print the embedded NF bitmap, then the firm code as normal ESC/POS text on the same line."""
        if not NF_LOGO_ESC_STAR:
            return False

        code = footer_logo_code.strip().upper()
        logo_x = getattr(style, "logo_x_offset", 0)
        # ESC * reserves a 24-dot band while this approved monogram is 14 dots high.
        # A seven-dot transparent top offset optically aligns it to the text baseline.
        logo_y = max(0, min(10, 7 + getattr(style, "logo_y_offset", 0)))
        gap = getattr(style, "code_gap", 2)
        code_x = getattr(style, "code_x_offset", 0)
        code_y = getattr(style, "code_y_offset", 0)
        code_align = getattr(style, "code_align", "left")
        win32print.WritePrinter(h_printer, b"\x1ba" + bytes([{"left": 0, "center": 1, "right": 2}.get(align, 1)]))
        if logo_x:
            relative = logo_x & 0xFFFF
            win32print.WritePrinter(h_printer, b"\x1b\\" + bytes([relative & 0xFF, relative >> 8]))
        command = NF_LOGO_ESC_STAR if not logo_y else _pack_esc_star_24dot(_build_logo_pixels(logo_y))
        win32print.WritePrinter(h_printer, command)
        if code:
            if code_x:
                relative = code_x & 0xFFFF
                win32print.WritePrinter(h_printer, b"\x1b\\" + bytes([relative & 0xFF, relative >> 8]))
            if code_align in {"center", "right"}:
                target = (192 - len(code) * 6) if code_align == "center" else (384 - len(code) * 12)
                target = max(0, target)
                win32print.WritePrinter(h_printer, b"\x1b$" + bytes([target & 0xFF, (target >> 8) & 0xFF]))
            if code_y > 0:
                win32print.WritePrinter(h_printer, b"\x1bJ" + bytes([code_y]))
            elif code_y < 0:
                win32print.WritePrinter(h_printer, b"\x1bj" + bytes([-code_y]))
            size = ((getattr(style, "code_width_scale", 1) - 1) << 4) | (getattr(style, "code_height_scale", 1) - 1)
            win32print.WritePrinter(h_printer, b"\x1bE" + bytes([1 if getattr(style, "code_bold", False) else 0]))
            win32print.WritePrinter(h_printer, b"\x1d!" + bytes([size]))
            win32print.WritePrinter(h_printer, (" " * gap + code).encode("cp857", errors="replace"))
        win32print.WritePrinter(h_printer, b"\n\x1ba\x00")
        print("NF bitmap logo printed")
        return True

    def save_txt(self, output_dir: Path, filename: str, content: str) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        return path
