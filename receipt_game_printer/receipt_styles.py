from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable

from complete_batch import firm_identity


STYLE_VERSION = 1
ALIGNMENTS = {"left", "center", "right"}
SCALES = {1, 2}
ROLES = (
    "firm_name", "sector", "address", "phone", "tax_office", "date", "time",
    "receipt_no", "product", "vat", "total", "payment", "trade_registry",
    "eku_z", "footer_logo",
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
        return "\n".join(block.text for block in self.blocks)


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


def validate_overrides(overrides: dict) -> None:
    for role, values in overrides.items():
        if role not in ROLES or not isinstance(values, dict):
            raise ValueError(f"Desteklenmeyen fiş rolü: {role}")
        unknown = set(values) - set(TextStyle.__dataclass_fields__)
        if unknown:
            raise ValueError(f"Desteklenmeyen stil alanı: {', '.join(sorted(unknown))}")
        validate_style(TextStyle(**values))


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
    capacity = max(width // style.width_scale, 1)
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
    result: list[ReceiptBlock] = []
    for block in blocks:
        style = styles.get(block.role, block.style)
        if not style.visible:
            continue
        source = block.text.strip() if style.align in {"center", "right"} else block.text
        text = fit_styled_text(source, style, width)
        if style.align == "center":
            text = text.center(max(width // style.width_scale, 1))
        elif style.align == "right":
            text = text.rjust(max(width // style.width_scale, 1))
        result.append(ReceiptBlock(text, block.role, style))
        for _ in range(style.line_spacing):
            result.append(ReceiptBlock("", block.role, TextStyle()))
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
