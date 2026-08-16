from __future__ import annotations

from pathlib import Path
from typing import List

from receipt_styles import StyledReceipt

try:
    import win32print
except ImportError:
    win32print = None


# ---------------------------------------------------------------------------
# NF LOGO
#
# "#" = siyah termal piksel
# "." = boş piksel
#
# Tek aktif NF logo implementasyonu.
# PNG / Pillow / Unicode / harici font kullanılmaz.
# ---------------------------------------------------------------------------

NF_LOGO_BITMAP = (
    "............##...........####################.....",
    "............###.........##....##..................",
    "...........##.##.......##.....##..................",
    "...........##.##......##......##..................",
    "..........##...##....##......##...................",
    "..........##....##...##.......#############.......",
    ".........##......##.##.......##...................",
    "........##........###.......##....................",
    "........##........##........##....................",
    "......##...................##.....................",
    "......##...................##.....................",
    ".....##...................##......................",
    "....##....................##......................",
    "...##....................##.......................",
    "...##....................##.......................",
    "........................##........................",
)

NF_LOGO_HEIGHT = len(NF_LOGO_BITMAP)
NF_LOGO_WIDTH = len(NF_LOGO_BITMAP[0])


def _build_logo_pixels(y_offset: int = 0) -> list[list[int]]:
    """
    Sabit NF bitmap'ini 1-bit piksel matrisine dönüştür.

    y_offset=0:
        Doğal 14 satırlık bitmap döner. Mevcut testler ve normal paketleme
        davranışı korunur.

    y_offset!=0:
        ESC * 24-dot bandı içinde logoya şeffaf üst/alt boşluk eklemek için
        24 satırlık bir canvas döner. NF geometrisi değiştirilmez; yalnızca
        bitmap bandı içindeki dikey konumu değişir.
    """
    if not NF_LOGO_BITMAP:
        raise ValueError("NF logo bitmap is empty")

    if NF_LOGO_WIDTH <= 0:
        raise ValueError("NF logo bitmap width must be greater than zero")

    if NF_LOGO_HEIGHT > 24:
        raise ValueError("NF logo bitmap height must be 24 pixels or less")

    if any(len(row) != NF_LOGO_WIDTH for row in NF_LOGO_BITMAP):
        raise ValueError("NF logo bitmap rows must have equal width")

    invalid_pixels = {
        pixel
        for row in NF_LOGO_BITMAP
        for pixel in row
        if pixel not in {"#", "."}
    }
    if invalid_pixels:
        raise ValueError("NF logo bitmap may contain only '#' and '.'")

    pixels = [
        [1 if pixel == "#" else 0 for pixel in row]
        for row in NF_LOGO_BITMAP
    ]

    if not y_offset:
        return pixels

    canvas = [
        [0] * NF_LOGO_WIDTH
        for _ in range(24)
    ]

    for y, row in enumerate(pixels):
        target = y + y_offset
        if 0 <= target < 24:
            canvas[target] = row[:]

    return canvas


def _pack_esc_star_24dot(
    pixels: list[list[int]],
) -> bytes:
    """1-bit bitmap'i ESC/POS ESC * 24-dot formatına dönüştür."""
    if not pixels:
        raise ValueError("Logo pixel matrix is empty")

    if not pixels[0]:
        raise ValueError("Logo pixel matrix width is zero")

    height = len(pixels)
    width = len(pixels[0])

    if height > 24:
        raise ValueError(
            "ESC * 24-dot logo height must be 24 pixels or less"
        )

    if any(len(row) != width for row in pixels):
        raise ValueError(
            "Logo pixel rows must have equal width"
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


def _signed_16(value: int) -> tuple[int, int]:
    """
    ESC/POS iki byte'lık relative-position değeri üretir.

    Negatif değerler two's-complement olarak paketlenir.
    """
    encoded = int(value) & 0xFFFF
    return encoded & 0xFF, (encoded >> 8) & 0xFF


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
        content: str | StyledReceipt,
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

                if isinstance(
                    content,
                    StyledReceipt,
                ):
                    self._write_styled_receipt(
                        h_printer,
                        content,
                    )
                else:
                    self._write_receipt_with_optional_logo(
                        h_printer,
                        content,
                    )

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
        [NF LOGO] placeholder'ını CP857'e çevrilmeden önce yakalar.

        Placeholder yazıcıya metin olarak gönderilmez.
        NF bitmap olarak basılır.
        Firma kodu bitmap'ten sonra CP857 text olarak aynı satırda kalır.
        """
        lines = content.splitlines()
        index = 0

        while index < len(lines):
            line = lines[index]
            stripped = line.strip()

            if stripped.startswith(
                "[NF LOGO]"
            ):
                footer_logo_code = (
                    stripped
                    .removeprefix("[NF LOGO]")
                    .strip()
                )

                # Eski formatta kod bir sonraki satırdaysa onu da destekle.
                if (
                    not footer_logo_code
                    and index + 1 < len(lines)
                ):
                    next_line = (
                        lines[index + 1]
                        .strip()
                    )

                    if next_line:
                        footer_logo_code = next_line
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

    def _write_styled_receipt(
        self,
        h_printer,
        receipt: StyledReceipt,
    ) -> None:
        """
        ReceiptBlock'ları izole ESC/POS stil komutlarıyla basar.

        Firma bazlı bold/size/alignment ayarlarının sonraki bloğa veya
        sonraki fişe sızmaması için her blok sonunda reset uygulanır.
        """
        # Her styled fişin başında güvenli ESC/POS reset.
        win32print.WritePrinter(
            h_printer,
            b"\x1b@",
        )

        align_codes = {
            "left": 0,
            "center": 1,
            "right": 2,
        }

        for block in receipt.blocks:
            stripped = block.text.strip()
            style = block.style

            if stripped.startswith(
                "[NF LOGO]"
            ):
                code = (
                    stripped
                    .removeprefix("[NF LOGO]")
                    .strip()
                )

                if not self.print_bitmap_logo(
                    h_printer,
                    code,
                    getattr(
                        style,
                        "align",
                        "center",
                    ),
                    style,
                ):
                    fallback = " ".join(
                        part
                        for part in (
                            "NF",
                            code,
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

                self._write_style_reset(
                    h_printer
                )
                continue

            align = align_codes.get(
                getattr(
                    style,
                    "align",
                    "left",
                ),
                0,
            )

            width_scale = (
                2
                if getattr(
                    style,
                    "width_scale",
                    1,
                ) == 2
                else 1
            )

            height_scale = (
                2
                if getattr(
                    style,
                    "height_scale",
                    1,
                ) == 2
                else 1
            )

            # GS !:
            # bits 4-7 = width multiplier - 1
            # bits 0-3 = height multiplier - 1
            size = (
                ((width_scale - 1) << 4)
                | (height_scale - 1)
            )

            win32print.WritePrinter(
                h_printer,
                b"\x1ba"
                + bytes([align]),
            )

            win32print.WritePrinter(
                h_printer,
                b"\x1bE"
                + bytes(
                    [
                        1
                        if getattr(
                            style,
                            "bold",
                            False,
                        )
                        else 0
                    ]
                ),
            )

            win32print.WritePrinter(
                h_printer,
                b"\x1d!"
                + bytes([size]),
            )

            same_line = bool(
                getattr(
                    style,
                    "same_line",
                    False,
                )
            )

            ending = (
                ""
                if same_line
                else "\n"
            )

            win32print.WritePrinter(
                h_printer,
                f"{block.text}{ending}".encode(
                    "cp857",
                    errors="replace",
                ),
            )

            # Bir bloğun stili sonraki bloğa taşınmasın.
            self._write_style_reset(
                h_printer
            )

            # same_line aktifken burada newline/spacing üretmeyiz.
            if not same_line:
                line_spacing = getattr(
                    style,
                    "line_spacing",
                    0,
                )

                if (
                    isinstance(
                        line_spacing,
                        int,
                    )
                    and line_spacing > 0
                ):
                    win32print.WritePrinter(
                        h_printer,
                        b"\n"
                        * min(
                            line_spacing,
                            3,
                        ),
                    )

        self._write_style_reset(
            h_printer
        )

    def _write_style_reset(
        self,
        h_printer,
    ) -> None:
        """
        Bold, character size ve alignment ayarlarını normale döndür.

        Not:
        Burada ESC @ kullanılmaz; aksi halde satır içi/pozisyon davranışları
        gereksiz yere tamamen sıfırlanabilir.
        """
        win32print.WritePrinter(
            h_printer,
            b"\x1bE\x00"
            b"\x1d!\x00"
            b"\x1ba\x00",
        )

    def print_bitmap_logo(
        self,
        h_printer,
        footer_logo_code: str = "",
        align: str = "center",
        style=None,
    ) -> bool:
        """
        NF bitmap logosunu ve firma logo kodunu aynı fiziksel satırda basar.

        Firma stilinden güvenli olarak okunabilen alanlar:
        - logo_x_offset
        - logo_y_offset
        - code_gap
        - code_x_offset
        - code_y_offset
        - code_align
        - code_bold
        - code_width_scale
        - code_height_scale

        NF_LOGO_BITMAP geometrisi değiştirilmez. logo_y_offset yalnızca
        24-dot bitmap bandındaki şeffaf üst/alt padding'i değiştirir.
        """
        if not NF_LOGO_ESC_STAR:
            return False

        code = (
            footer_logo_code
            .strip()
            .upper()
        )

        align_code = {
            "left": 0,
            "center": 1,
            "right": 2,
        }.get(
            align,
            1,
        )

        logo_x = int(
            getattr(
                style,
                "logo_x_offset",
                0,
            )
            or 0
        )

        # 14-dot logo, ESC * modunda 24-dot bantta basılıyor.
        # Varsayılan 7-dot şeffaf üst boşluk, metin ile optik baseline'ı
        # yakınlaştırır. Firma override'ı bu değeri ince ayarlar.
        requested_logo_y = int(
            getattr(
                style,
                "logo_y_offset",
                0,
            )
            or 0
        )

        logo_y = max(
            0,
            min(
                10,
                7 + requested_logo_y,
            ),
        )

        gap = max(
            0,
            min(
                10,
                int(
                    getattr(
                        style,
                        "code_gap",
                        2,
                    )
                    or 0
                ),
            ),
        )

        code_x = int(
            getattr(
                style,
                "code_x_offset",
                0,
            )
            or 0
        )

        code_y = int(
            getattr(
                style,
                "code_y_offset",
                0,
            )
            or 0
        )

        code_align = getattr(
            style,
            "code_align",
            "left",
        )

        code_width_scale = (
            2
            if getattr(
                style,
                "code_width_scale",
                1,
            ) == 2
            else 1
        )

        code_height_scale = (
            2
            if getattr(
                style,
                "code_height_scale",
                1,
            ) == 2
            else 1
        )

        code_size = (
            ((code_width_scale - 1) << 4)
            | (code_height_scale - 1)
        )

        try:
            # Logo satırının genel hizası.
            win32print.WritePrinter(
                h_printer,
                b"\x1ba"
                + bytes([align_code]),
            )

            # Firma bazlı yatay logo ince ayarı.
            if logo_x:
                n_l, n_h = _signed_16(
                    logo_x
                )

                win32print.WritePrinter(
                    h_printer,
                    b"\x1b\\"
                    + bytes(
                        [n_l, n_h]
                    ),
                )

            command = (
                NF_LOGO_ESC_STAR
                if logo_y == 0
                else _pack_esc_star_24dot(
                    _build_logo_pixels(
                        logo_y
                    )
                )
            )

            win32print.WritePrinter(
                h_printer,
                command,
            )

            if code:
                if code_x:
                    n_l, n_h = _signed_16(
                        code_x
                    )

                    win32print.WritePrinter(
                        h_printer,
                        b"\x1b\\"
                        + bytes(
                            [n_l, n_h]
                        ),
                    )

                # code_align logo satırı içinde kodun mutlak konumunu
                # değiştirmek için opsiyonel bir ince ayardır.
                #
                # 58 mm / 384-dot sınıfı yazıcı varsayımı mevcut uygulamanın
                # hedef donanımıyla uyumludur. "left" seçildiğinde hiçbir
                # mutlak pozisyon komutu gönderilmez.
                if code_align in {
                    "center",
                    "right",
                }:
                    estimated_char_width = (
                        12
                        * code_width_scale
                    )

                    if code_align == "center":
                        target = (
                            384
                            - (
                                len(code)
                                * estimated_char_width
                            )
                        ) // 2
                    else:
                        target = (
                            384
                            - (
                                len(code)
                                * estimated_char_width
                            )
                        )

                    target = max(
                        0,
                        min(
                            383,
                            target,
                        ),
                    )

                    win32print.WritePrinter(
                        h_printer,
                        b"\x1b$"
                        + bytes(
                            [
                                target & 0xFF,
                                (
                                    target >> 8
                                )
                                & 0xFF,
                            ]
                        ),
                    )

                # Dikey code offset yalnızca kullanıcı gerçekten vermişse
                # uygulanır. Bazı ESC/POS modellerinde ESC J/j davranışı
                # değişebildiği için varsayılan değer sıfırdır.
                if code_y > 0:
                    win32print.WritePrinter(
                        h_printer,
                        b"\x1bJ"
                        + bytes(
                            [
                                min(
                                    code_y,
                                    255,
                                )
                            ]
                        ),
                    )

                elif code_y < 0:
                    win32print.WritePrinter(
                        h_printer,
                        b"\x1bj"
                        + bytes(
                            [
                                min(
                                    -code_y,
                                    255,
                                )
                            ]
                        ),
                    )

                win32print.WritePrinter(
                    h_printer,
                    b"\x1bE"
                    + bytes(
                        [
                            1
                            if getattr(
                                style,
                                "code_bold",
                                False,
                            )
                            else 0
                        ]
                    ),
                )

                win32print.WritePrinter(
                    h_printer,
                    b"\x1d!"
                    + bytes(
                        [code_size]
                    ),
                )

                # Logo ile kod arasında newline yok:
                # bitmap -> gap -> code -> newline
                win32print.WritePrinter(
                    h_printer,
                    (
                        (" " * gap)
                        + code
                    ).encode(
                        "cp857",
                        errors="replace",
                    ),
                )

            # Satır ancak logo + code tamamlandıktan sonra biter.
            self._write_style_reset(
                h_printer
            )

            win32print.WritePrinter(
                h_printer,
                b"\n",
            )

            print(
                "NF bitmap logo printed"
            )

            return True

        except Exception:
            # Çağıran katman güvenli ASCII "NF ..." fallback'i basabilir.
            try:
                self._write_style_reset(
                    h_printer
                )
            except Exception:
                pass

            return False

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
