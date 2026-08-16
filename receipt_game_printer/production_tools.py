from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Iterable, Sequence

from complete_batch import FirmReceiptJob, PairKey, firm_identity
from vat_engine import calculate_vat
from vat_engine import validate_vat_integrity


def valid_step_values(minimum: float, maximum: float, step: int | None) -> list[float]:
    if minimum > maximum:
        raise ValueError("Minimum tutar maksimumdan büyük olamaz")
    if not step:
        return []
    first = math.ceil(minimum / step) * step
    last = math.floor(maximum / step) * step
    if first > last:
        raise ValueError(f"Tutar aralığında {step} katı kullanılabilir değer yok")
    return [float(value) for value in range(first, last + 1, step)]


def generate_amount(
    minimum: float,
    maximum: float,
    step_mode: int | None = None,
    rng: random.Random | None = None,
) -> float:
    rng = rng or random
    if step_mode:
        return rng.choice(valid_step_values(minimum, maximum, step_mode))
    if minimum > maximum:
        raise ValueError("Minimum tutar maksimumdan büyük olamaz")
    return round(rng.uniform(minimum, maximum), 2)


def generate_smart_amounts(
    count: int,
    minimum: float,
    maximum: float,
    step_mode: int | None = None,
    rng: random.Random | None = None,
) -> list[float]:
    if count < 0:
        raise ValueError("Fiş sayısı negatif olamaz")
    rng = rng or random.Random()
    if step_mode:
        universe = valid_step_values(minimum, maximum, step_mode)
        bucket_size = math.ceil(len(universe) / 3)
        buckets = [universe[index * bucket_size:(index + 1) * bucket_size] for index in range(3)]
    else:
        if minimum > maximum:
            raise ValueError("Minimum tutar maksimumdan büyük olamaz")
        span = maximum - minimum
        boundaries = [minimum, minimum + span / 3, minimum + 2 * span / 3, maximum]
        buckets = [(boundaries[index], boundaries[index + 1]) for index in range(3)]
    if any(not bucket for bucket in buckets):
        # A very narrow step range cannot populate all thirds; retain valid values.
        buckets = [bucket or (universe if step_mode else (minimum, maximum)) for bucket in buckets]
    amounts: list[float] = []
    recent: list[float] = []
    order = [index % 3 for index in range(count)]
    rng.shuffle(order)
    for bucket_index in order:
        bucket = buckets[bucket_index]
        for _attempt in range(5):
            value = rng.choice(bucket) if step_mode else round(rng.uniform(*bucket), 2)
            only_choice = step_mode is not None and len(set(bucket)) == 1
            if value not in recent[-3:] or only_choice:
                break
        amounts.append(value)
        recent.append(value)
    return amounts


@dataclass(frozen=True)
class PlannedReceipt:
    job: FirmReceiptJob
    amount: float


def build_normal_batch_plan(
    firms: Sequence[object],
    count: int,
    start_receipt_no: int,
    mode: str,
    excluded_firm_ids: Iterable[str] = (),
    max_per_firm: int | None = None,
    no_repeat: bool = False,
    minimum_amount: float = 0,
    maximum_amount: float = 0,
    step_mode: int | None = None,
    smart_distribution: bool = False,
    fixed_amount: float | None = None,
    firm_amounts: bool = False,
    rng: random.Random | None = None,
) -> list[PlannedReceipt]:
    if count <= 0:
        raise ValueError("Fiş sayısı 0'dan büyük olmalı")
    rng = rng or random.Random()
    excluded = set(excluded_firm_ids)
    active: list[object] = []
    seen: set[str] = set()
    for firm in firms:
        firm_id = firm_identity(firm)
        if firm_id not in excluded and firm_id not in seen:
            seen.add(firm_id)
            active.append(firm)
    if not active:
        raise ValueError("Bütün firmalar seri baskıdan hariç tutulmuş")
    if max_per_firm is not None and max_per_firm <= 0:
        raise ValueError("Firma başına maksimum fiş 0'dan büyük olmalı")
    if max_per_firm and count > len(active) * max_per_firm:
        raise ValueError(
            f"Seçilen {len(active)} firma ve firma başına {max_per_firm} fiş limiti ile "
            f"maksimum {len(active) * max_per_firm} fiş üretilebilir."
        )
    usage = {firm_identity(firm): 0 for firm in active}
    selected: list[object] = []
    previous_id: str | None = None
    for index in range(count):
        available = [firm for firm in active if not max_per_firm or usage[firm_identity(firm)] < max_per_firm]
        if no_repeat and previous_id and len(available) > 1:
            alternatives = [firm for firm in available if firm_identity(firm) != previous_id]
            if alternatives:
                available = alternatives
        if mode == "Tek firma":
            firm = active[0]
            if firm not in available:
                raise ValueError("Tek firma seçimi firma başına maksimum limite ulaştı")
        elif mode == "Sırayla":
            firm = min(available, key=lambda item: (usage[firm_identity(item)], active.index(item)))
        else:
            firm = rng.choice(available)
        selected.append(firm)
        previous_id = firm_identity(firm)
        usage[previous_id] += 1

    if fixed_amount is not None:
        amounts = [fixed_amount] * count
    elif firm_amounts:
        amounts = [float(getattr(firm, "default_amount")) for firm in selected]
    elif smart_distribution:
        amounts = generate_smart_amounts(count, minimum_amount, maximum_amount, step_mode, rng)
    else:
        amounts = [generate_amount(minimum_amount, maximum_amount, step_mode, rng) for _ in range(count)]
    return [
        PlannedReceipt(FirmReceiptJob(firm, firm_identity(firm), start_receipt_no + index), amounts[index])
        for index, firm in enumerate(selected)
    ]


@dataclass
class FinancialItem:
    firm_id: str
    firm_name: str
    count: int = 0
    total_amount: Decimal = Decimal("0")
    total_vat: Decimal = Decimal("0")

    @property
    def average_amount(self) -> Decimal:
        return Decimal("0") if not self.count else self.total_amount / self.count


class FinancialSummary:
    def __init__(self):
        self.items: dict[str, FinancialItem] = {}
        self._counted_tokens: set[str] = set()

    def add_success(self, token: str, firm_id: str, firm_name: str, amount: float, vat_rate: float) -> bool:
        if token in self._counted_tokens:
            return False
        self._counted_tokens.add(token)
        item = self.items.setdefault(firm_id, FinancialItem(firm_id, firm_name))
        item.count += 1
        item.total_amount += Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        item.total_vat += Decimal(str(calculate_vat(amount, vat_rate))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return True

    def as_dict(self) -> dict:
        return {
            firm_id: {"firm_name": item.firm_name, "count": item.count,
                      "total_amount": str(item.total_amount), "total_vat": str(item.total_vat),
                      "average_amount": str(item.average_amount.quantize(Decimal('0.01')))}
            for firm_id, item in self.items.items()
        }

    def totals(self) -> dict:
        return {
            "count": sum(item.count for item in self.items.values()),
            "total_amount": sum((item.total_amount for item in self.items.values()), Decimal("0")),
            "total_vat": sum((item.total_vat for item in self.items.values()), Decimal("0")),
        }


@dataclass
class PreflightResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def run_preflight(
    *, printer_name: str, printer_exists: Callable[[str], bool], firms: Sequence[object],
    requested_count: int, start_no: int, end_no: int, minimum_amount: float,
    maximum_amount: float, step_mode: int | None, max_per_firm: int | None,
    excluded_count: int, history_loader: Callable[[], set[PairKey]], batch_active: bool,
    pending_active: bool, template_validator: Callable[[], None], bitmap_ready: bool,
    dry_run: bool = False, vat_checks: Iterable[tuple[float, float, float | None]] = (),
) -> PreflightResult:
    result = PreflightResult()
    if not firms:
        result.errors.append("Firma listesi boş")
    if start_no > end_no:
        result.errors.append("Başlangıç fiş no bitiş fiş no değerinden büyük")
    if minimum_amount > maximum_amount:
        result.errors.append("Minimum tutar maksimumdan büyük")
    if step_mode:
        try:
            valid_step_values(minimum_amount, maximum_amount, step_mode)
        except ValueError as exc:
            result.errors.append(str(exc))
    if max_per_firm and requested_count > len(firms) * max_per_firm:
        result.errors.append("Firma başına maksimum limit kapasitesi yetersiz")
    if batch_active:
        result.errors.append("Başka bir batch halen aktif")
    if not printer_name or not printer_exists(printer_name):
        (result.warnings if dry_run else result.errors).append("Yazıcı seçilmedi veya erişilemiyor")
    try:
        history_loader()
    except (OSError, ValueError) as exc:
        result.errors.append(str(exc))
    try:
        template_validator()
    except ValueError as exc:
        result.errors.append(f"Şablon geçersiz: {exc}")
    if not bitmap_ready:
        result.errors.append("NF bitmap üretilemiyor")
    if pending_active:
        result.warnings.append("Tamamlanmamış başka bir baskı kuyruğu var")
    if any(not getattr(firm, "eku_no", "") or not getattr(firm, "z_no", "") for firm in firms):
        result.warnings.append("Bazı firmalarda EKU/Z alanı boş; şablon varsayılanı kullanılabilir")
    if any(not getattr(firm, "footer_logo_code", "") for firm in firms):
        result.warnings.append("Bazı firmalarda alt logo kodu boş")
    if excluded_count:
        result.info.append(f"Hariç tutulan firma: {excluded_count}")
    try:
        for amount, rate, rendered in vat_checks:
            validate_vat_integrity(amount, rate, rendered)
    except ValueError as exc:
        result.errors.append(str(exc))
    else:
        result.info.append("KDV hesaplama bütünlüğü doğrulandı")
    result.info.append(f"Planlanan fiş: {requested_count}")
    return result


@dataclass
class DryRunResult:
    planned_jobs: list[PlannedReceipt]
    skipped: int
    warnings: list[str]
    financial_summary: dict


def build_dry_run(plan: list[PlannedReceipt], skipped: int, warnings: list[str], vat_rate: float) -> DryRunResult:
    summary = FinancialSummary()
    for index, item in enumerate(plan):
        summary.add_success(f"dry-{index}", item.job.firm_id, getattr(item.job.firm, "name", item.job.firm_id),
                            item.amount, vat_rate)
    return DryRunResult(plan, skipped, warnings, summary.as_dict())


def search_records(records: Iterable[dict], **filters) -> list[dict]:
    result = []
    for record in records:
        if filters.get("firm_id") and record.get("firm_id") != filters["firm_id"]:
            continue
        if filters.get("firm") and filters["firm"].casefold() not in str(record.get("firm_name", "")).casefold():
            continue
        number = record.get("receipt_no")
        if filters.get("start_no") is not None and (number is None or number < filters["start_no"]):
            continue
        if filters.get("end_no") is not None and (number is None or number > filters["end_no"]):
            continue
        amount = record.get("amount")
        if filters.get("min_amount") is not None and (amount is None or amount < filters["min_amount"]):
            continue
        if filters.get("max_amount") is not None and (amount is None or amount > filters["max_amount"]):
            continue
        timestamp = str(record.get("timestamp", ""))
        if filters.get("date_from") and timestamp < filters["date_from"]:
            continue
        if filters.get("date_to") and timestamp > filters["date_to"]:
            continue
        if filters.get("vat_rate") is not None and record.get("vat_rate") != filters["vat_rate"]:
            continue
        if filters.get("manual_reprint") is not None and bool(record.get("manual_reprint")) != filters["manual_reprint"]:
            continue
        for key in ("session_id", "status", "mode"):
            if filters.get(key) and record.get(key) != filters[key]:
                break
        else:
            result.append(record)
    return result
