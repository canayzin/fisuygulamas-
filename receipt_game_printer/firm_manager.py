import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List


@dataclass
class Firm:
    name: str
    sector: str
    address: str
    game_code: str
    default_product: str
    default_vat: float
    default_amount: float


DEFAULT_FIRMS = [
    Firm("A TAMIRCISI", "YEDEK PARCA", "M SINAN MAH USKUDAR CD NO:59", "OYK-001", "YEDEK PARCA", 20.0, 3750.0),
    Firm("B MARKET", "MARKET ALISVERISI", "ATATURK CAD NO:11", "OYK-002", "MARKET URUNU", 10.0, 420.0),
    Firm("C BENZINLIK", "AKARYAKIT", "CEVRE YOLU KM 5", "OYK-003", "AKARYAKIT", 20.0, 1250.0),
    Firm("D ECZANE", "ILAC", "SAGLIK SOK NO:8", "OYK-004", "ILAC", 10.0, 890.0),
    Firm("E RESTORAN", "YEMEK", "LEZZET CAD NO:27", "OYK-005", "YEMEK SERVISI", 10.0, 640.0),
]


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
            self.firms = [Firm(**item) for item in raw]
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
