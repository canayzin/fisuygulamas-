from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ReceiptTemplate:
    header_lines: list[str]
    footer_lines: list[str]
    eku_format: str
    z_no: str
    separator_char: str
    width: int
    center_firm_name: bool
    product_line_format: str
    show_vat: bool
    show_time: bool
    show_receipt_no: bool
    show_footer: bool
    show_phone: bool
    show_phone2: bool
    show_website: bool
    show_tax_office: bool
    phone_position: str


def default_template() -> ReceiptTemplate:
    return ReceiptTemplate(
        header_lines=[],
        footer_lines=[],
        eku_format="EKU NO: {game_code}",
        z_no="707",
        separator_char="-",
        width=32,
        center_firm_name=True,
        product_line_format="{product}",
        show_vat=True,
        show_time=True,
        show_receipt_no=True,
        show_footer=True,
        show_phone=True,
        show_phone2=False,
        show_website=False,
        show_tax_office=False,
        phone_position="address_below",
    )


class TemplateManager:
    def __init__(self, json_path: Path):
        self.json_path = Path(json_path)
        self.template = default_template()

    def load(self) -> ReceiptTemplate:
        if not self.json_path.exists():
            self.template = default_template()
            self.save()
            return self.template
        try:
            data = json.loads(self.json_path.read_text(encoding="utf-8"))
            base = asdict(default_template())
            base.update(data)
            self.template = ReceiptTemplate(**base)
            validate_template(self.template)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self.template = default_template()
        return self.template

    def save(self, template: ReceiptTemplate | None = None) -> None:
        if template is not None:
            validate_template(template)
            self.template = template
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        self.json_path.write_text(json.dumps(asdict(self.template), indent=2, ensure_ascii=False), encoding="utf-8")

    def reset(self) -> ReceiptTemplate:
        self.template = default_template()
        return self.template


def validate_template(template: ReceiptTemplate) -> None:
    if template.width < 20 or template.width > 48:
        raise ValueError("Fiş genişliği geçersiz")
    if template.phone_position not in {"address_above", "address_below", "date_above"}:
        template.phone_position = "address_below"
    if not template.separator_char:
        template.separator_char = "-"
    template.separator_char = template.separator_char[0]
