from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from textwrap import wrap

from template_manager import ReceiptTemplate, default_template, validate_template
from receipt_styles import ReceiptBlock, StyledReceipt, TextStyle, apply_styles, resolve_role_styles, template_with_style_visibility
from vat_engine import calculate_vat


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
    address_line1: str = ""
    address_line2: str = ""
    phone1: str = ""
    phone2: str = ""
    website: str = ""
    tax_office: str = ""
    trade_registry_no: str = ""
    eku_no: str = ""
    z_no: str = ""
    footer_logo_code: str = ""


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


def _wrap_line(text: str, width: int) -> list[str]:
    if not text:
        return []
    return wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [text[:width]]


def _format_product_line(data: ReceiptData, amount_text: str, width: int) -> str:
    product = data.product_name[: max(width - 14, 8)]
    vat = f"%{int(data.vat_rate)}"
    amount_col = amount_text[-10:]
    middle_width = max(width - len(product) - len(vat) - len(amount_col), 2)
    left_gap = max(middle_width // 2, 1)
    right_gap = max(middle_width - left_gap, 1)
    return f"{product}{' ' * left_gap}{vat}{' ' * right_gap}{amount_col}"[:width]


def _contact_lines(data: ReceiptData, template: ReceiptTemplate) -> list[str]:
    lines: list[str] = []
    if template.show_phone and data.phone1:
        lines.append(f"TEL: {data.phone1}")
    if template.show_phone2 and data.phone2:
        lines.append(f"TEL 2: {data.phone2}")
    if template.show_website and data.website:
        lines.append(f"WEB: {data.website}")
    if template.show_tax_office and data.tax_office:
        lines.append(data.tax_office)
    return lines


def _address_lines(data: ReceiptData, template: ReceiptTemplate, width: int) -> list[str]:
    source = [line for line in [data.address_line1, data.address_line2] if line] or ([data.address] if data.address else [])
    if not template.wrap_address:
        return [_fit_line(line, width) for line in source]
    lines: list[str] = []
    for line in source:
        lines.extend(_wrap_line(line, width))
    return lines


def _format_receipt_no(data: ReceiptData, template: ReceiptTemplate) -> str:
    return f"{data.receipt_no:06d}" if template.receipt_no_zero_pad else str(data.receipt_no)


def _footer_logo_lines(data: ReceiptData, template: ReceiptTemplate, width: int) -> list[str]:
    if not template.show_footer_logo:
        return []
    if template.use_bitmap_nf_logo:
        logo_line = "  ".join(part for part in ["[NF LOGO]", data.footer_logo_code] if part).strip()
        return [center(logo_line, width)]

    logo_line = "  ".join(part for part in ["NF", data.footer_logo_code] if part).strip()
    return [center(logo_line, width)] if logo_line else []


def build_receipt_blocks(data: ReceiptData, template: ReceiptTemplate | None = None) -> list[ReceiptBlock]:
    template = template or default_template()
    validate_template(template)
    width = template.width
    vat_amount = calculate_vat(data.amount, data.vat_rate)
    separator = (template.separator_char or ".")[0] * min(width, max(width - 2, 1))

    blocks: list[ReceiptBlock] = []

    def add(text: str, role: str = "product"):
        blocks.append(ReceiptBlock(text, role, TextStyle()))

    for header in template.header_lines:
        add(_fit_line(header, width), "header")
    if template.header_lines and not template.header_compact:
        add("", "separator")

    for text, role in [(data.firm_name, "firm_name"), (data.sector, "sector")]:
        if text:
            add(center(text, width) if template.center_firm_name else _fit_line(text, width), role)
    address_rows = _address_lines(data, template, width)
    for index, text in enumerate(address_rows):
        role = "address_line1" if index == 0 else "address_line2"
        add(center(text, width) if template.center_firm_name else _fit_line(text, width), role)
    for text in _contact_lines(data, template):
        if text == data.tax_office:
            role = "tax_office"
        elif data.website and data.website in text:
            role = "website"
        elif data.phone2 and data.phone2 in text:
            role = "phone2"
        else:
            role = "phone1"
        add(center(text, width) if template.center_firm_name else _fit_line(text, width), role)
    add("", "separator")

    add(data.dt.strftime("%d-%m-%Y"), "date")
    if template.show_time:
        add(f"SAAT: {data.dt.strftime('%H:%M')}", "time")
    if template.show_receipt_no:
        add(f"FIS NO : {_format_receipt_no(data, template)}", "receipt_no")
    add("", "separator")

    add(_format_product_line(data, format_money(data.amount), width), "product")
    add(separator, "separator1")
    if template.show_vat:
        add(left_right("TOPKDV", format_money(vat_amount), width), "vat")
    add(left_right("TOPLAM", format_money(data.amount), width), "total")
    add(separator, "separator2")
    add(left_right(data.payment_type, format_money(data.amount), width), "payment")

    if template.show_trade_registry_no and data.trade_registry_no:
        add(f"T.SICIL NO:{data.trade_registry_no}"[:width], "trade_registry")

    eku_no = data.eku_no if template.use_firm_eku_z and data.eku_no else template.eku_no
    z_no = data.z_no if template.use_firm_eku_z and data.z_no else template.z_no
    try:
        eku_text = template.eku_format.format(game_code=eku_no, receipt_no=_format_receipt_no(data, template), eku_no=eku_no)
    except (KeyError, ValueError):
        eku_text = f"EKU NO: {eku_no}"
    add(left_right(eku_text, f"Z NO: {z_no}", width), "eku_z")

    if template.show_footer and template.footer_lines:
        add("", "separator")
        for footer in template.footer_lines:
            add(_fit_line(footer, width), "footer")
    for logo in _footer_logo_lines(data, template, width):
        add(logo, "footer_logo")
    add("", "separator")
    return blocks


def build_receipt_text(data: ReceiptData, template: ReceiptTemplate | None = None) -> str:
    return "\n".join(block.text for block in build_receipt_blocks(data, template))


def build_styled_receipt(data: ReceiptData, template: ReceiptTemplate, overrides: dict | None = None) -> StyledReceipt:
    effective_template = template_with_style_visibility(template, overrides)
    blocks = build_receipt_blocks(data, effective_template)
    split_blocks: list[ReceiptBlock] = []
    split_roles = {
        "vat": ("vat_label", "vat_amount"), "total": ("total_label", "total_amount"),
        "payment": ("payment_type", "payment_amount"),
    }
    for block in blocks:
        if block.role == "product" and "%" in block.text and "*" in block.text:
            percent = block.text.find("%")
            star = block.text.rfind("*")
            split_blocks.extend([
                ReceiptBlock(block.text[:percent], "product_name", TextStyle()),
                ReceiptBlock(block.text[percent:star], "vat_rate", TextStyle()),
                ReceiptBlock(block.text[star:], "product_amount", TextStyle()),
            ])
            continue
        if block.role == "eku_z" and "Z NO:" in block.text:
            z_at = block.text.find("Z NO:")
            left = block.text[:z_at]
            eku_colon = left.find(":")
            z_text = block.text[z_at:]
            z_colon = z_text.find(":")
            split_blocks.extend([
                ReceiptBlock(left[:eku_colon + 1], "eku_label", TextStyle()),
                ReceiptBlock(left[eku_colon + 1:], "eku_value", TextStyle()),
                ReceiptBlock(z_text[:z_colon + 1], "z_label", TextStyle()),
                ReceiptBlock(z_text[z_colon + 1:], "z_value", TextStyle()),
            ])
            continue
        if block.role not in split_roles or "*" not in block.text:
            split_blocks.append(block)
            continue
        label_role, amount_role = split_roles[block.role]
        star = block.text.rfind("*")
        label = block.text[:star]
        amount = block.text[star:]
        split_blocks.append(ReceiptBlock(label, label_role, TextStyle()))
        split_blocks.append(ReceiptBlock(amount, amount_role, TextStyle()))
    blocks = split_blocks
    if (overrides or {}).get("custom_text"):
        blocks.append(ReceiptBlock("", "custom_text", TextStyle()))
    styles = resolve_role_styles(effective_template, overrides)
    return apply_styles(blocks, styles, effective_template.width)
