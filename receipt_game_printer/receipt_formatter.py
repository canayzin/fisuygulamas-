from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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


def center(text: str) -> str:
    return text[:RECEIPT_WIDTH].center(RECEIPT_WIDTH)


def left_right(left: str, right: str) -> str:
    left = left[:RECEIPT_WIDTH]
    space = RECEIPT_WIDTH - len(left) - len(right)
    if space < 1:
        left = left[: RECEIPT_WIDTH - len(right) - 1]
        space = 1
    return f"{left}{' ' * space}{right}"


def build_receipt_text(data: ReceiptData) -> str:
    vat_amount = data.amount * data.vat_rate / (100 + data.vat_rate)
    line = "-" * 30
    rows = [
        center(data.firm_name),
        center(data.sector),
        center(data.address),
        "",
        f"TARIH: {data.dt.strftime('%d-%m-%Y')}",
        f"SAAT : {data.dt.strftime('%H:%M:%S')}",
        f"FIS NO: {data.receipt_no:06d}",
        "",
        line,
        left_right(data.product_name, format_money(data.amount)),
        left_right(f"KDV %{int(data.vat_rate)}", format_money(vat_amount)),
        line,
        left_right("TOPLAM", format_money(data.amount)),
        "",
        f"ODEME: {data.payment_type}",
        "",
        left_right(f"EKU NO: {data.game_code}", "Z NO: 707"),
        "",
        "*** OYUN AMACLIDIR ***",
        "TICARI GECERLILIGI YOKTUR",
        "",
    ]
    return "\n".join(rows)
