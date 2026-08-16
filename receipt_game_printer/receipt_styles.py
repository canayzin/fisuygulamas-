from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from complete_batch import firm_identity


STYLE_VERSION = 2
ALIGNMENTS = {"left", "center", "right"}
SCALES = {1, 2}
ROLES = (
    "firm_name", "sector", "address", "address_line1", "address_line2", "phone", "phone1",
    "phone2", "website", "tax_office", "trade_registry", "date", "time", "receipt_no",
    "product", "product_name", "vat_rate", "product_amount", "separator1", "vat",
    "vat_label", "vat_amount", "total", "total_label", "total_amount", "separator2",
    "payment", "payment_type", "payment_amount", "eku_z", "eku_label", "eku_value",
    "z_label", "z_value", "footer_logo", "logo_code", "footer", "custom_text",
)


@dataclass(frozen=True)
class TextStyle:
    bold: bool = False
    width_scale: int = 1
    height_scale: int = 1
    align: str = "left"
    visible: bool = True
    wrap: bool | None = None
    line_spacing: int = 0
    x_offset: int = 0
    y_offset: int = 0
    space_before: int = 0
    space_after: int = 0
    prefix: str = ""
    suffix: str = ""
    text_override: str = ""
    order: int = 0
    row: str = ""
    same_line: bool = False
    column_width: int = 0
    locked: bool = False
    logo_x_offset: int = 0
    logo_y_offset: int = 0
    code_gap: int = 2
    code_x_offset: int = 0
    code_y_offset: int = 0
    code_bold: bool = False
    code_align: str = "left"
    code_width_scale: int = 1
    code_height_scale: int = 1


@dataclass(frozen=True)
class ReceiptBlock:
    text: str
    role: str
    style: TextStyle


@dataclass(frozen=True)
class StyledReceipt:
    blocks: tuple[ReceiptBlock, ...]
    width: int = 32

    def plain_text(self) -> str:
        if not any(block.style.same_line for block in self.blocks):
            return "\n".join(block.text for block in self.blocks)
        lines: list[str] = []
        current = ""
        for block in self.blocks:
            current += block.text
            if not block.style.same_line:
                lines.append(current)
                current = ""
        if current:
            lines.append(current)
        return "\n".join(lines)


def validate_style(style: TextStyle) -> None:
    if not isinstance(style.bold, bool) or not isinstance(style.visible, bool):
        raise ValueError("bold ve visible boolean olmalı")
    if style.width_scale not in SCALES or style.height_scale not in SCALES:
        raise ValueError("Yazı ölçeği yalnızca 1 veya 2 olabilir")
    if style.align not in ALIGNMENTS:
        raise ValueError("Hizalama left, center veya right olmalı")
    if style.line_spacing < 0 or style.line_spacing > 3:
        raise ValueError("Satır aralığı 0-3 arasında olmalı")
    if style.wrap is not None and not isinstance(style.wrap, bool):
        raise ValueError("wrap boolean olmalı")
    if not -20 <= style.x_offset <= 20 or not -8 <= style.y_offset <= 8:
        raise ValueError("Alan offset değerleri desteklenen aralığın dışında")
    if not 0 <= style.space_before <= 5 or not 0 <= style.space_after <= 5:
        raise ValueError("Alan boşlukları 0-5 arasında olmalı")
    if not -20 <= style.logo_x_offset <= 20 or not -8 <= style.logo_y_offset <= 8:
        raise ValueError("Logo offset değerleri desteklenen aralığın dışında")
    if not 0 <= style.code_gap <= 10 or not -20 <= style.code_x_offset <= 20 or not -8 <= style.code_y_offset <= 8:
        raise ValueError("Logo kodu konum değerleri geçersiz")
    if style.code_width_scale not in SCALES or style.code_height_scale not in SCALES:
        raise ValueError("Logo kodu ölçeği yalnızca 1 veya 2 olabilir")
    if style.code_align not in ALIGNMENTS:
        raise ValueError("Logo kodu hizalaması geçersiz")
    if not 0 <= style.column_width <= 48:
        raise ValueError("Kolon genişliği 0-48 arasında olmalı")


def validate_overrides(overrides: dict) -> None:
    for role, values in overrides.items():
        if role not in ROLES or not isinstance(values, dict):
            raise ValueError(f"Desteklenmeyen fiş rolü: {role}")
        unknown = set(values) - set(TextStyle.__dataclass_fields__)
        if unknown:
            raise ValueError(f"Desteklenmeyen stil alanı: {', '.join(sorted(unknown))}")
        validate_style(TextStyle(**values))
    for critical in ("total_amount", "payment_amount"):
        if overrides.get(critical, {}).get("visible") is False:
            raise ValueError(f"Kritik parasal alan gizlenemez: {critical}")


def validate_layout(overrides: dict, width: int, money_samples: Iterable[str] = ()) -> None:
    validate_overrides(overrides)
    if not 20 <= width <= 48:
        raise ValueError("Fiş genişliği 20-48 arasında olmalı")
    for role in ("vat_amount", "total_amount", "payment_amount"):
        values = overrides.get(role, {})
        capacity = width // int(values.get("width_scale", 1)) - max(int(values.get("x_offset", 0)), 0)
        for value in money_samples:
            if len(value) > capacity:
                raise ValueError(f"Parasal değer safe area dışına taşıyor: {role} / {value}")


def default_role_styles(template) -> dict[str, TextStyle]:
    centered = "center" if template.center_firm_name else "left"
    styles = {
        role: TextStyle(align=centered if role in {"firm_name", "sector", "address", "phone", "tax_office"} else "left")
        for role in ROLES
    }
    styles["address"] = replace(styles["address"], wrap=template.wrap_address)
    styles["phone"] = replace(styles["phone"], visible=template.show_phone)
    styles["tax_office"] = replace(styles["tax_office"], visible=template.show_tax_office)
    styles["trade_registry"] = replace(styles["trade_registry"], visible=template.show_trade_registry_no)
    styles["footer_logo"] = replace(styles["footer_logo"], visible=template.show_footer_logo)
    for alias, source in {
        "address_line1": "address", "address_line2": "address", "phone1": "phone", "phone2": "phone",
        "website": "phone", "vat_label": "vat", "vat_amount": "vat", "total_label": "total",
        "total_amount": "total", "payment_type": "payment", "payment_amount": "payment",
        "logo_code": "footer_logo", "eku_label": "eku_z", "eku_value": "eku_z",
        "z_label": "eku_z", "z_value": "eku_z", "product_name": "product",
        "vat_rate": "product", "product_amount": "product",
    }.items():
        styles[alias] = replace(styles[source])
    for label in ("product_name", "vat_rate", "vat_label", "total_label", "payment_type", "eku_label", "eku_value", "z_label"):
        styles[label] = replace(styles[label], same_line=True)
    return styles


def resolve_role_styles(template, overrides: dict | None) -> dict[str, TextStyle]:
    styles = default_role_styles(template)
    for role, values in (overrides or {}).items():
        if role not in styles:
            continue
        merged = asdict(styles[role])
        merged.update(values)
        style = TextStyle(**merged)
        validate_style(style)
        styles[role] = style
    for parent, children in {
        "address": ("address_line1", "address_line2"), "phone": ("phone1", "phone2", "website"),
        "product": ("product_name", "vat_rate", "product_amount"),
        "vat": ("vat_label", "vat_amount"), "total": ("total_label", "total_amount"),
        "payment": ("payment_type", "payment_amount"), "eku_z": ("eku_label", "eku_value", "z_label", "z_value"),
        "footer_logo": ("logo_code",),
    }.items():
        if parent not in (overrides or {}):
            continue
        parent_values = (overrides or {})[parent]
        for child in children:
            if child in (overrides or {}):
                continue
            merged = asdict(styles[child]); merged.update(parent_values)
            styles[child] = TextStyle(**merged)
    return styles


def template_with_style_visibility(template, overrides: dict | None):
    overrides = overrides or {}
    mapping = {
        "phone": "show_phone", "tax_office": "show_tax_office",
        "trade_registry": "show_trade_registry_no", "footer_logo": "show_footer_logo",
    }
    changes = {}
    for role, field in mapping.items():
        if "visible" in overrides.get(role, {}):
            changes[field] = bool(overrides[role]["visible"])
    if "wrap" in overrides.get("address", {}):
        changes["wrap_address"] = bool(overrides["address"]["wrap"])
    return replace(template, **changes) if changes else template


def fit_styled_text(text: str, style: TextStyle, width: int) -> str:
    logical_width = style.column_width or width
    capacity = max(logical_width // style.width_scale, 1)
    if len(text) <= capacity:
        return text
    if "*" in text:
        star = text.rfind("*")
        amount = text[star:]
        label = text[:star].strip()
        if len(amount) >= capacity:
            return amount
        return f"{label[:capacity - len(amount) - 1]} {amount}".strip()
    return text[:capacity]


def apply_styles(blocks: Iterable[ReceiptBlock], styles: dict[str, TextStyle], width: int) -> StyledReceipt:
    source_blocks = list(blocks)
    indexed = list(enumerate(source_blocks))
    if any(styles.get(block.role, block.style).order for block in source_blocks):
        indexed.sort(key=lambda pair: (styles.get(pair[1].role, pair[1].style).order or 10000 + pair[0], pair[0]))
    result: list[ReceiptBlock] = []
    for _index, block in indexed:
        style = styles.get(block.role, block.style)
        if not style.visible:
            continue
        base_text = style.text_override if style.text_override else block.text
        source = f"{style.prefix}{base_text}{style.suffix}"
        source = source.strip() if style.align in {"center", "right"} else source
        text = fit_styled_text(source, style, width)
        if style.align == "center":
            text = text.center(max((style.column_width or width) // style.width_scale, 1))
        elif style.align == "right":
            text = text.rjust(max((style.column_width or width) // style.width_scale, 1))
        if style.x_offset > 0:
            text = " " * style.x_offset + text
        elif style.x_offset < 0:
            text = text[min(-style.x_offset, len(text)):]
        for _ in range(style.space_before + max(style.y_offset, 0)):
            result.append(ReceiptBlock("", "separator", TextStyle()))
        result.append(ReceiptBlock(text, block.role, style))
        for _ in range(style.line_spacing):
            result.append(ReceiptBlock("", block.role, TextStyle()))
        for _ in range(style.space_after + max(-style.y_offset, 0)):
            result.append(ReceiptBlock("", "separator", TextStyle()))
    return StyledReceipt(tuple(result), width)


class FirmReceiptStyleStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.profiles: dict[str, dict] = {}

    def load(self) -> dict[str, dict]:
        if not self.path.exists():
            self.profiles = {}
            return self.profiles
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            version = int(payload.get("version", 1))
            if version > STYLE_VERSION:
                raise ValueError("Fiş stil dosyası daha yeni bir sürüme ait")
            firms = payload.get("firms", {})
            if not isinstance(firms, dict):
                raise ValueError("Fiş stil dosyası geçersiz")
            for profile in firms.values():
                validate_overrides(profile)
            if version < STYLE_VERSION:
                backup = self.path.with_suffix(self.path.suffix + f".v{version}.bak")
                if not backup.exists():
                    backup.write_bytes(self.path.read_bytes())
            # Version 1 profiles are already sparse role dictionaries. Version 2 only
            # adds optional fields, so migration is lossless and idempotent.
            self.profiles = firms
            return copy.deepcopy(self.profiles)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Firma fiş stilleri okunamadı: {self.path.name}") from exc

    def save(self) -> None:
        for profile in self.profiles.values():
            validate_overrides(profile)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"version": STYLE_VERSION, "firms": self.profiles}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def get(self, firm_or_id) -> dict:
        key = firm_or_id if isinstance(firm_or_id, str) else firm_identity(firm_or_id)
        return copy.deepcopy(self.profiles.get(key, {}))

    def set(self, firm_or_id, overrides: dict) -> None:
        validate_overrides(overrides)
        key = firm_or_id if isinstance(firm_or_id, str) else firm_identity(firm_or_id)
        if overrides:
            self.profiles[key] = copy.deepcopy(overrides)
        else:
            self.profiles.pop(key, None)

    def copy_style(self, source, targets: Iterable[object]) -> None:
        profile = self.get(source)
        for target in targets:
            self.set(target, profile)
        self.save()


class StyleUndoManager:
    def __init__(self, initial: dict, limit: int = 100):
        self.limit = limit
        self.undo_stack: list[dict] = [copy.deepcopy(initial)]
        self.redo_stack: list[dict] = []

    @property
    def current(self) -> dict:
        return copy.deepcopy(self.undo_stack[-1])

    def push(self, state: dict) -> None:
        if state == self.undo_stack[-1]:
            return
        self.undo_stack.append(copy.deepcopy(state))
        self.undo_stack = self.undo_stack[-self.limit:]
        self.redo_stack.clear()

    def undo(self) -> dict:
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
        return self.current

    def redo(self) -> dict:
        if self.redo_stack:
            self.undo_stack.append(self.redo_stack.pop())
        return self.current
