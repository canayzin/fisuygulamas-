from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from complete_batch import (
    FirmReceiptJob,
    PairKey,
    build_missing_firm_receipt_jobs,
    firm_identity,
)


def get_last_receipt_numbers(
    history: Iterable[PairKey],
) -> dict[str, int]:
    result: dict[str, int] = {}

    for firm_id, receipt_no in history:
        firm_key = str(firm_id)
        receipt_number = int(receipt_no)

        result[firm_key] = max(
            result.get(
                firm_key,
                receipt_number,
            ),
            receipt_number,
        )

    return result


def get_last_receipt_number_for_firm(
    firm_id: str,
    history: Iterable[PairKey],
) -> int | None:
    return get_last_receipt_numbers(
        history
    ).get(
        str(firm_id)
    )


def build_matrix_status(
    firms: Sequence[object],
    start_no: int,
    end_no: int,
    history: Iterable[PairKey],
    failed_pairs: Iterable[PairKey] = (),
) -> dict[PairKey, str]:
    if start_no > end_no:
        raise ValueError(
            "Başlangıç fiş no, bitiş fiş no değerinden büyük olamaz"
        )

    printed = set(history)
    failed = set(failed_pairs)

    result: dict[PairKey, str] = {}

    for firm in firms:
        firm_id = firm_identity(firm)

        for receipt_no in range(
            start_no,
            end_no + 1,
        ):
            pair = (
                firm_id,
                receipt_no,
            )

            if pair in printed:
                result[pair] = "printed"
            elif pair in failed:
                result[pair] = "failed"
            else:
                result[pair] = "missing"

    return result


def build_balanced_print_jobs(
    firms: Sequence[object],
    start_receipt_no: int,
    requested_count: int,
    used_pairs: Iterable[PairKey],
) -> list[FirmReceiptJob]:
    if not firms:
        raise ValueError(
            "Firma listesi boş"
        )

    if requested_count <= 0:
        raise ValueError(
            "İstenen fiş sayısı 0'dan büyük olmalı"
        )

    used = set(
        used_pairs
    )

    unique: dict[str, object] = {}

    for firm in firms:
        unique.setdefault(
            firm_identity(firm),
            firm,
        )

    counts = {
        firm_id: sum(
            1
            for pair in used
            if pair[0] == firm_id
        )
        for firm_id in unique
    }

    next_numbers = {
        firm_id: start_receipt_no
        for firm_id in unique
    }

    jobs: list[FirmReceiptJob] = []
    reserved: set[PairKey] = set()

    while len(jobs) < requested_count:
        firm_id = min(
            unique,
            key=lambda item: (
                counts[item],
                item,
            ),
        )

        receipt_no = (
            next_numbers[firm_id]
        )

        while (
            (firm_id, receipt_no) in used
            or (firm_id, receipt_no) in reserved
        ):
            receipt_no += 1

        next_numbers[firm_id] = (
            receipt_no + 1
        )

        job = FirmReceiptJob(
            unique[firm_id],
            firm_id,
            receipt_no,
        )

        jobs.append(
            job
        )

        reserved.add(
            job.pair_key
        )

        counts[firm_id] += 1

    return jobs


def build_filtered_jobs(
    firms: Sequence[object],
    start_no: int,
    end_no: int,
    used_pairs: Iterable[PairKey],
    manual_reprint: bool,
) -> list[FirmReceiptJob]:
    return build_missing_firm_receipt_jobs(
        firms,
        start_no,
        end_no,
        () if manual_reprint else used_pairs,
        randomize=False,
    )


@dataclass
class IntegrityResult:
    expected: int
    successful: int
    missing_jobs: list[FirmReceiptJob]

    @property
    def missing(self) -> int:
        return len(
            self.missing_jobs
        )


def check_integrity(
    firms: Sequence[object],
    start_no: int,
    end_no: int,
    history: Iterable[PairKey],
) -> IntegrityResult:
    missing = build_missing_firm_receipt_jobs(
        firms,
        start_no,
        end_no,
        history,
        randomize=False,
    )

    firm_count = len(
        {
            firm_identity(firm)
            for firm in firms
        }
    )

    expected = (
        firm_count
        * (
            end_no
            - start_no
            + 1
        )
    )

    return IntegrityResult(
        expected=expected,
        successful=expected - len(missing),
        missing_jobs=missing,
    )


class AtomicJsonStore:
    def __init__(
        self,
        path: Path,
        default,
    ):
        self.path = Path(
            path
        )

        self.default = default
        self._lock = threading.Lock()

    def load(self):
        with self._lock:
            if not self.path.exists():
                return self.default.copy()

            try:
                return json.loads(
                    self.path.read_text(
                        encoding="utf-8"
                    )
                )

            except (
                OSError,
                json.JSONDecodeError,
            ) as exc:
                raise ValueError(
                    f"Veri dosyası okunamadı: {self.path.name}"
                ) from exc

    def save(
        self,
        payload,
    ) -> None:
        with self._lock:
            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary = (
                self.path.with_suffix(
                    self.path.suffix
                    + ".tmp"
                )
            )

            temporary.write_text(
                json.dumps(
                    payload,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            temporary.replace(
                self.path
            )


class FailureStore:
    def __init__(
        self,
        path: Path,
    ):
        self.store = AtomicJsonStore(
            path,
            [],
        )

    def active(
        self,
    ) -> list[dict]:
        return [
            item
            for item in self.store.load()
            if not item.get(
                "resolved_at"
            )
        ]

    def active_pairs(
        self,
    ) -> set[PairKey]:
        return {
            (
                str(item["firm_id"]),
                int(item["receipt_no"]),
            )
            for item in self.active()
        }

    def record(
        self,
        pair: PairKey,
        error: str,
        session_id: str,
    ) -> None:
        items = (
            self.store.load()
        )

        now = datetime.now(
            timezone.utc
        ).isoformat()

        for item in items:
            item_pair = (
                str(
                    item.get(
                        "firm_id"
                    )
                ),
                int(
                    item.get(
                        "receipt_no"
                    )
                ),
            )

            if (
                item_pair == pair
                and not item.get(
                    "resolved_at"
                )
            ):
                item.update(
                    timestamp=now,
                    error=error,
                    session_id=session_id,
                )

                self.store.save(
                    items
                )

                return

        items.append(
            {
                "firm_id": pair[0],
                "receipt_no": pair[1],
                "timestamp": now,
                "error": error,
                "session_id": session_id,
                "resolved_at": None,
            }
        )

        self.store.save(
            items
        )

    def resolve(
        self,
        pair: PairKey,
    ) -> None:
        items = (
            self.store.load()
        )

        now = datetime.now(
            timezone.utc
        ).isoformat()

        for item in items:
            item_pair = (
                str(
                    item.get(
                        "firm_id"
                    )
                ),
                int(
                    item.get(
                        "receipt_no"
                    )
                ),
            )

            if (
                item_pair == pair
                and not item.get(
                    "resolved_at"
                )
            ):
                item["resolved_at"] = now

        self.store.save(
            items
        )


class SessionStore:
    def __init__(
        self,
        path: Path,
    ):
        self.store = AtomicJsonStore(
            path,
            [],
        )

    def create(
        self,
        mode: str,
        jobs: Sequence[FirmReceiptJob],
        start_no: int,
        end_no: int,
        randomize: bool,
        skipped: int = 0,
        reprint_count: int = 0,
    ) -> dict:
        session = {
            "session_id": uuid.uuid4().hex,
            "mode": mode,
            "started_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "finished_at": None,

            "selected_firm_ids": sorted(
                {
                    job.firm_id
                    for job in jobs
                }
            ),

            "start_receipt_no": start_no,
            "end_receipt_no": end_no,

            "planned_count": len(
                jobs
            ),

            "successful_count": 0,
            "failed_count": 0,
            "skipped_count": skipped,
            "reprint_count": reprint_count,

            "status": "RUNNING",
            "randomize": randomize,

            "successful_pairs": [],
            "failed_pairs": [],

            "pair_details_truncated": False,

            # Production planning / safety metadata
            "amount_step_mode": None,
            "smart_amount_distribution": False,
            "max_per_firm": None,
            "excluded_firm_ids": [],
            "preflight_summary": {},
            "financial_summary": {},
            "dry_run": False,
            "style_profile_version": 2,
        }
        sessions = self.store.load()
        sessions.append(session)
        self.store.save(sessions)
        return session

    def update(self, session: dict) -> None:
        sessions = self.store.load()
        for index, item in enumerate(sessions):
            if item.get("session_id") == session["session_id"]:
                sessions[index] = session
                break
        else:
            sessions.append(session)
        self.store.save(sessions)

    def list(self) -> list[dict]:
        return self.store.load()


class PendingBatchStore:
    def __init__(self, path: Path):
        self.store = AtomicJsonStore(path, {})

    def save(self, session_id: str, mode: str, jobs: Sequence[FirmReceiptJob], allow_reprint: bool = False) -> None:
        self.store.save({"session_id": session_id, "mode": mode,
                         "allow_reprint": allow_reprint,
                         "pending": [[job.firm_id, job.receipt_no] for job in jobs]})

    def load(self) -> dict:
        return self.store.load()

    def clear(self) -> None:
        self.store.save({})


class PrintRecordStore:
    """Search metadata index; successful-pair truth remains PrintHistory."""

    def __init__(self, path: Path):
        self.store = AtomicJsonStore(path, [])

    def append(self, record: dict) -> None:
        records = self.store.load()
        records.append(record)
        self.store.save(records)

    def list(self) -> list[dict]:
        return self.store.load()


def remove_jobs(jobs: Sequence[FirmReceiptJob], indexes: Iterable[int]) -> list[FirmReceiptJob]:
    removed = set(indexes)
    return [job for index, job in enumerate(jobs) if index not in removed]


def filter_pending_jobs(jobs: Sequence[FirmReceiptJob], used_pairs: Iterable[PairKey]) -> list[FirmReceiptJob]:
    """Drop jobs completed through any route before a paused queue resumes."""
    used = set(used_pairs)
    return [job for job in jobs if job.pair_key not in used]
