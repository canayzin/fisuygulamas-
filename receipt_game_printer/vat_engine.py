from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import re


CENT = Decimal("0.01")


def calculate_vat(amount: float | Decimal, vat_rate: float | Decimal) -> Decimal:
    """Apply the project rule amount * rate / 100 and round half-up to cents."""
    value = Decimal(str(amount))
    rate = Decimal(str(vat_rate))
    if value < 0 or rate < 0:
        raise ValueError("Tutar ve KDV oranı negatif olamaz")
    return (value * rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class VatIntegrity:
    amount: Decimal
    vat_rate: Decimal
    expected_vat: Decimal
    rendered_vat: Decimal

    @property
    def valid(self) -> bool:
        return abs(self.expected_vat - self.rendered_vat) <= CENT


def validate_vat_integrity(amount, vat_rate, rendered_vat=None) -> VatIntegrity:
    expected = calculate_vat(amount, vat_rate)
    rendered = expected if rendered_vat is None else Decimal(str(rendered_vat)).quantize(CENT, rounding=ROUND_HALF_UP)
    result = VatIntegrity(Decimal(str(amount)), Decimal(str(vat_rate)), expected, rendered)
    if not result.valid:
        raise ValueError(
            "KDV doğrulaması başarısız.\n"
            f"Tutar: {result.amount:.2f} TL\nKDV oranı: %{result.vat_rate:g}\n"
            f"Beklenen KDV: {result.expected_vat:.2f} TL\nHesaplanan KDV: {result.rendered_vat:.2f} TL\n"
            "Fiş güvenlik nedeniyle basılmadı."
        )
    return result


def extract_rendered_vat(content) -> Decimal | None:
    text = content.plain_text() if hasattr(content, "plain_text") else str(content)
    match = re.search(r"TOPKDV[^*]*\*([0-9.]+,[0-9]{2})", text)
    if not match:
        return None
    normalized = match.group(1).replace(".", "").replace(",", ".")
    return Decimal(normalized)


def validate_text_receipt_vat(content) -> VatIntegrity | None:
    text = content.plain_text() if hasattr(content, "plain_text") else str(content)
    rendered = extract_rendered_vat(text)
    if rendered is None:
        return None
    total_match = re.search(r"TOPLAM[^*]*\*([0-9.]+,[0-9]{2})", text)
    rate_match = re.search(r"%\s*([0-9]+(?:[.,][0-9]+)?)", text)
    if not total_match or not rate_match:
        raise ValueError("KDV doğrulaması için fiş tutarı veya KDV oranı bulunamadı")
    amount = Decimal(total_match.group(1).replace(".", "").replace(",", "."))
    rate = Decimal(rate_match.group(1).replace(",", "."))
    return validate_vat_integrity(amount, rate, rendered)


def validated_print(printer_service, printer_name, content, amount, vat_rate, rendered_vat=None) -> None:
    """Validate VAT immediately before invoking the hardware printing path."""
    actual = extract_rendered_vat(content) if rendered_vat is None else rendered_vat
    validate_vat_integrity(amount, vat_rate, actual)
    printer_service.print_raw(printer_name, content)
