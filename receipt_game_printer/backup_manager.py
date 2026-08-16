from __future__ import annotations

import hashlib
import json
import shutil
import threading
from datetime import datetime
from pathlib import Path


class BackupManager:
    def __init__(self, base_dir: Path, filenames: list[str], retention: int = 20):
        self.base_dir = Path(base_dir)
        self.backup_dir = self.base_dir / "backups"
        self.filenames = filenames
        self.retention = retention
        self._lock = threading.Lock()

    def create(self, reason: str) -> Path:
        with self._lock:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
            destination = self.backup_dir / f"backup_{timestamp}"
            destination.mkdir(parents=True)
            manifest = {"created_at": datetime.now().isoformat(), "reason": reason, "files": {}}
            for filename in self.filenames:
                source = self.base_dir / filename
                if not source.exists():
                    continue
                data = source.read_bytes()
                (destination / filename).write_bytes(data)
                manifest["files"][filename] = hashlib.sha256(data).hexdigest()
            (destination / "manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self._prune()
            return destination

    def list_backups(self) -> list[Path]:
        if not self.backup_dir.exists():
            return []
        return sorted((path for path in self.backup_dir.iterdir() if path.is_dir()), reverse=True)

    def validate(self, backup: Path) -> dict:
        try:
            manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
            for filename, checksum in manifest["files"].items():
                data = (backup / filename).read_bytes()
                if hashlib.sha256(data).hexdigest() != checksum:
                    raise ValueError(f"Yedek checksum hatası: {filename}")
                if filename.endswith(".json"):
                    json.loads(data.decode("utf-8"))
            return manifest
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("Yedek bozuk veya eksik") from exc

    def restore(self, backup: Path) -> Path:
        with self._lock:
            manifest = self.validate(backup)
            # The lock is already held, so create the emergency snapshot inline.
            emergency = self.backup_dir / f"backup_{datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')}_emergency"
            emergency.mkdir(parents=True)
            emergency_manifest = {"created_at": datetime.now().isoformat(), "reason": "restore öncesi emergency", "files": {}}
            for filename in self.filenames:
                current = self.base_dir / filename
                if current.exists():
                    data = current.read_bytes()
                    (emergency / filename).write_bytes(data)
                    emergency_manifest["files"][filename] = hashlib.sha256(data).hexdigest()
            (emergency / "manifest.json").write_text(json.dumps(emergency_manifest, indent=2), encoding="utf-8")
            staged: list[tuple[Path, Path]] = []
            for filename in manifest["files"]:
                target = self.base_dir / filename
                temporary = target.with_suffix(target.suffix + ".restore")
                shutil.copy2(backup / filename, temporary)
                staged.append((temporary, target))
            for temporary, target in staged:
                temporary.replace(target)
            self._prune()
            return emergency

    def _prune(self):
        backups = self.list_backups()
        for old in backups[self.retention:]:
            shutil.rmtree(old)
