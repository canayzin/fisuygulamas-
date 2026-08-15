import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List


@dataclass
class Firm:
    name: str
    sector: str
    address_line1: str
    address_line2: str
    phone1: str
    phone2: str
    website: str
    tax_office: str
    trade_registry_no: str
    eku_no: str
    z_no: str
    footer_logo_code: str
    game_code: str
    default_product: str
    default_vat: float
    default_amount: float

    @property
    def address(self) -> str:
        return " ".join(part for part in [self.address_line1, self.address_line2] if part).strip()


DEFAULT_FIRMS = [
    Firm("A TAMIRCISI", "YEDEK PARCA", "M SINAN MAH USKUDAR CD NO:59", "", "0216 111 11 11", "", "", "", "", "", "", "", "OYK-001", "YEDEK PARCA", 20.0, 3750.0),
    Firm("B MARKET", "MARKET ALISVERISI", "ATATURK CAD NO:11", "", "0216 222 22 22", "", "", "", "", "", "", "", "OYK-002", "MARKET URUNU", 10.0, 420.0),
    Firm("C BENZINLIK", "AKARYAKIT", "CEVRE YOLU KM 5", "", "0216 333 33 33", "", "", "", "", "", "", "", "OYK-003", "AKARYAKIT", 20.0, 1250.0),
    Firm("D ECZANE", "ILAC", "SAGLIK SOK NO:8", "", "0216 444 44 44", "", "", "", "", "", "", "", "OYK-004", "ILAC", 10.0, 890.0),
    Firm("E RESTORAN", "YEMEK", "LEZZET CAD NO:27", "", "0216 555 55 55", "", "", "", "", "", "", "", "OYK-005", "YEMEK SERVISI", 10.0, 640.0),
]


def firm_from_dict(item: dict) -> Firm:
    legacy_address = item.get("address", "")
    return Firm(
        name=item.get("name", ""),
        sector=item.get("sector", ""),
        address_line1=item.get("address_line1", legacy_address),
        address_line2=item.get("address_line2", ""),
        phone1=item.get("phone1", item.get("phone", "")),
        phone2=item.get("phone2", ""),
        website=item.get("website", ""),
        tax_office=item.get("tax_office", ""),
        trade_registry_no=item.get("trade_registry_no", ""),
        eku_no=item.get("eku_no", ""),
        z_no=item.get("z_no", ""),
        footer_logo_code=item.get("footer_logo_code", ""),
        game_code=item.get("game_code", ""),
        default_product=item.get("default_product", ""),
        default_vat=float(item.get("default_vat", 20.0)),
        default_amount=float(item.get("default_amount", 100.0)),
    )


class FirmManager:
    def __init__(self, json_path: Path):
        self.json_path = Path(json_path)
        self.firms: List[Firm] = []

    def load(self) -> List[Firm]:
        if not self.json_path.exists():
            self.firms = list(DEFAULT_FIRMS)
            self.save()
            return self.firms

        try:
            raw = json.loads(self.json_path.read_text(encoding="utf-8"))
            self.firms = [firm_from_dict(item) for item in raw]
            if not self.firms:
                self.firms = list(DEFAULT_FIRMS)
                self.save()
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            self.firms = list(DEFAULT_FIRMS)
            self.save()
        return self.firms

    def save(self) -> None:
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(firm) for firm in self.firms]
        self.json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def add_firm(self, firm: Firm) -> None:
        self.firms.append(firm)

    def update_firm(self, index: int, firm: Firm) -> None:
        self.firms[index] = firm

    def delete_firm(self, index: int) -> None:
        del self.firms[index]
