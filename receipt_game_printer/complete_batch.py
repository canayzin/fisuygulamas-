from __future__ import annotations

import hashlib
import json
import random
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


PairKey = tuple[str, int]


def firm_identity(firm: object) -> str:
    """Return the most stable available identifier for a firm."""
    explicit_id = str(getattr(firm, "firm_id", "") or "").strip()
    if explicit_id:
        return explicit_id
    game_code = str(getattr(firm, "game_code", "") or "").strip()
    if game_code:
        return game_code
    identity_source = "|".join(
        str(getattr(firm, field, "") or "").strip().casefold()
        for field in ("name", "address_line1", "address_line2", "phone1")
    )
    return "legacy-" + hashlib.sha256(identity_source.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class FirmReceiptJob:
    firm: object
    firm_id: str
    receipt_no: int

    @property
    def pair_key(self) -> PairKey:
        return self.firm_id, self.receipt_no


def build_missing_firm_receipt_jobs(
    firms: Sequence[object],
    start_receipt_no: int,
    end_receipt_no: int,
    used_pairs: Iterable[PairKey],
    randomize: bool = True,
    rng: random.Random | None = None,
) -> list[FirmReceiptJob]:
    """Build every missing firm/number pair once, then optionally shuffle it."""
    if not firms:
        raise ValueError("Firma listesi boş")
    if start_receipt_no > end_receipt_no:
        raise ValueError("Başlangıç fiş no, bitiş fiş no değerinden büyük olamaz")

    used = {(str(firm_id), int(receipt_no)) for firm_id, receipt_no in used_pairs}
    unique_firms: list[tuple[str, object]] = []
    seen_firm_ids: set[str] = set()
    for firm in firms:
        firm_id = firm_identity(firm)
        if firm_id not in seen_firm_ids:
            seen_firm_ids.add(firm_id)
            unique_firms.append((firm_id, firm))

    jobs = [
        FirmReceiptJob(firm=firm, firm_id=firm_id, receipt_no=receipt_no)
        for receipt_no in range(start_receipt_no, end_receipt_no + 1)
        for firm_id, firm in unique_firms
        if (firm_id, receipt_no) not in used
    ]
    if randomize:
        (rng or random).shuffle(jobs)
    return jobs


class PrintHistory:
    """Persistent ledger whose unique key is (firm_id, receipt_no)."""

    def __init__(self, json_path: Path):
        self.json_path = Path(json_path)
        self._lock = threading.Lock()

    def load_pairs(self) -> set[PairKey]:
        with self._lock:
            return self._load_pairs_unlocked()

    def _load_pairs_unlocked(self) -> set[PairKey]:
        if not self.json_path.exists():
            return set()
        try:
            raw = json.loads(self.json_path.read_text(encoding="utf-8"))
            return {
                (str(item["firm_id"]), int(item["receipt_no"]))
                for item in raw
                if isinstance(item, dict) and "firm_id" in item and "receipt_no" in item
            }
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"Baskı geçmişi okunamadı: {self.json_path.name}") from exc

    def record_printed(self, pair: PairKey) -> bool:
        """Atomically add a successfully printed pair; return False if it exists."""
        normalized = str(pair[0]), int(pair[1])
        with self._lock:
            pairs = self._load_pairs_unlocked()
            if normalized in pairs:
                return False
            pairs.add(normalized)
            payload = [
                {"firm_id": firm_id, "receipt_no": receipt_no}
                for firm_id, receipt_no in sorted(pairs, key=lambda item: (item[0], item[1]))
            ]
            self.json_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.json_path.with_suffix(self.json_path.suffix + ".tmp")
            temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.json_path)
            return True
