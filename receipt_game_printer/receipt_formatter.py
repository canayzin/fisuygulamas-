from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from template_manager import ReceiptTemplate, default_template, validate_template


RECEIPT_WIDTH = 32


@dataclass
class ReceiptData:
    firm_name: str
    sector: str
    address: str
    game_code: str
    receipt_no: int
    dt: datetime
    product_name: str
    vat_rate: float
    amount: float
    payment_type: str


def format_money(value: float) -> str:
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"*{formatted}"


def center(text: str, width: int = RECEIPT_WIDTH) -> str:
    return text[:width].center(width)


def left_right(left: str, right: str, width: int = RECEIPT_WIDTH) -> str:
    left = left[:width]
    space = width - len(left) - len(right)
    if space < 1:
        left = left[: max(width - len(right) - 1, 0)]
        space = 1
    return f"{left}{' ' * space}{right}"[:width]


def _fit_line(text: str, width: int) -> str:
    return text[:width]


def _format_product_line(template: ReceiptTemplate, data: ReceiptData, amount_text: str) -> str:
    try:
        rendered = template.product_line_format.format(product=data.product_name, amount=amount_text)
    except (KeyError, ValueError):
        rendered = f"{data.product_name} {amount_text}"
    if "{amount}" not in template.product_line_format:
        return left_right(rendered, amount_text, template.width)
    return _fit_line(rendered, template.width)


def build_receipt_text(data: ReceiptData, template: ReceiptTemplate | None = None) -> str:
    template = template or default_template()
    validate_template(template)
    width = template.width
    vat_amount = data.amount * data.vat_rate / (100 + data.vat_rate)
    line = template.separator_char * min(width, max(width - 2, 1))

    rows: list[str] = []
    rows.extend(_fit_line(header, width) for header in template.header_lines)
    if template.header_lines:
        rows.append("")

    firm_line = center(data.firm_name, width) if template.center_firm_name else _fit_line(data.firm_name, width)
    rows.extend([firm_line, center(data.sector, width), center(data.address, width), ""])
    rows.append(f"TARIH: {data.dt.strftime('%d-%m-%Y')}")
    if template.show_time:
        rows.append(f"SAAT : {data.dt.strftime('%H:%M:%S')}")
    if template.show_receipt_no:
        rows.append(f"FIS NO: {data.receipt_no:06d}")
    rows.extend(["", line])

    rows.append(_format_product_line(template, data, format_money(data.amount)))
    if template.show_vat:
        rows.append(left_right(f"KDV %{int(data.vat_rate)}", format_money(vat_amount), width))
    rows.extend([line, left_right("TOPLAM", format_money(data.amount), width), "", f"ODEME: {data.payment_type}", ""])

    try:
        eku_text = template.eku_format.format(game_code=data.game_code, receipt_no=f"{data.receipt_no:06d}")
    except (KeyError, ValueError):
        eku_text = f"EKU NO: {data.game_code}"
    rows.append(left_right(eku_text, f"Z NO: {template.z_no}", width))

    if template.show_footer and template.footer_lines:
        rows.append("")
        rows.extend(_fit_line(footer, width) for footer in template.footer_lines)
    rows.append("")
    return "\n".join(rows)
