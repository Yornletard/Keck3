"""File d'attente locale persistée des contrôles à transmettre à Open Prod.

Chaque contrôle est écrit sur disque **avant** toute tentative d'envoi, puis rejoué
par le thread de publication (``run.py``) jusqu'à acceptation :

- ``data/outbox/<clé>.json`` : en attente (rejoué avec attente croissante) ;
- supprimé une fois accepté par Open Prod ;
- ``data/outbox/failed/<clé>.json`` : refus définitif, gardé pour arbitrage humain.

La clé d'idempotence (``type:série:horodatage[:voie]``) évite de mettre deux fois en
file la même trame ; le publisher vérifie de son côté l'existence dans Open Prod avant
de créer, ce qui rend le rejeu sûr après un timeout.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from api.models import ControlData, control_from_dict, control_to_dict
from core.logger import setup_logger

logger = setup_logger(__name__)

FAILED_DIR = 'failed'


def idempotency_key(kind: str, control: ControlData) -> str:
    key = f"{kind}:{control.serial_number}:{control.datetime.strftime('%Y%m%dT%H%M%S')}"
    way = getattr(control, 'way_number', None)
    if way is not None:
        key += f":V{way}"
    return key.replace('/', '_').replace('\\', '_')


@dataclass
class OutboxEntry:
    key: str
    kind: str
    serial_number: str
    control: Dict[str, Any]
    frame: List[List[str]]
    created_at: str
    attempts: int = 0
    last_error: Optional[str] = None
    path: Optional[Path] = field(default=None, compare=False, repr=False)

    def to_control(self) -> ControlData:
        return control_from_dict(self.kind, self.control)

    def to_json(self) -> str:
        data = asdict(self)
        data.pop('path')
        return json.dumps(data, ensure_ascii=False, indent=1)


class Outbox:
    """Stockage disque des contrôles en attente, un fichier par contrôle."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.failed_directory = self.directory / FAILED_DIR
        self.directory.mkdir(parents=True, exist_ok=True)
        self.failed_directory.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- write
    @staticmethod
    def _write(path: Path, entry: OutboxEntry) -> None:
        tmp = path.with_suffix('.json.tmp')
        tmp.write_text(entry.to_json(), encoding='utf-8')
        os.replace(tmp, path)

    def add(self, kind: str, control: ControlData, frame: Optional[Sequence[Sequence[str]]] = None) -> Optional[OutboxEntry]:
        """Met un contrôle en file. ``None`` si la même trame y est déjà (ou déjà refusée)."""
        key = idempotency_key(kind, control)
        path = self.directory / f"{key}.json"
        if path.exists() or (self.failed_directory / f"{key}.json").exists():
            logger.warning(f"Contrôle {key} déjà en file, ignoré")
            return None
        entry = OutboxEntry(
            key=key, kind=kind, serial_number=control.serial_number,
            control=control_to_dict(control),
            frame=[list(line) for line in (frame or [])],
            created_at=datetime.now().isoformat(timespec='seconds'),
            path=path,
        )
        self._write(path, entry)
        return entry

    # ----------------------------------------------------------------- read
    def _load(self, path: Path) -> Optional[OutboxEntry]:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            entry = OutboxEntry(**{k: v for k, v in data.items() if k != 'path'})
            entry.path = path
            entry.to_control()  # valide le contenu
            return entry
        except (OSError, ValueError, TypeError, KeyError) as e:
            logger.error(f"Entrée de file illisible {path.name}, déplacée dans {FAILED_DIR}/: {e}")
            try:
                os.replace(path, self.failed_directory / path.name)
            except OSError:
                pass
            return None

    def pending(self) -> List[OutboxEntry]:
        """Entrées en attente, dans l'ordre d'arrivée."""
        entries = [self._load(p) for p in self.directory.glob('*.json')]
        return sorted((e for e in entries if e is not None), key=lambda e: (e.created_at, e.key))

    def counts(self) -> Tuple[int, int]:
        """(en attente, refusés)."""
        return (len(list(self.directory.glob('*.json'))), len(list(self.failed_directory.glob('*.json'))))

    # --------------------------------------------------------------- update
    def mark_done(self, entry: OutboxEntry) -> None:
        if entry.path is not None:
            try:
                entry.path.unlink()
            except FileNotFoundError:
                pass

    def mark_retry(self, entry: OutboxEntry, error: Optional[str]) -> None:
        entry.attempts += 1
        entry.last_error = error
        if entry.path is not None:
            try:
                self._write(entry.path, entry)
            except OSError as e:
                logger.error(f"Impossible de mettre à jour {entry.path.name}: {e}")

    def mark_failed(self, entry: OutboxEntry, error: Optional[str]) -> None:
        entry.attempts += 1
        entry.last_error = error
        if entry.path is not None:
            target = self.failed_directory / entry.path.name
            try:
                self._write(target, entry)
                entry.path.unlink(missing_ok=True)
            except OSError as e:
                logger.error(f"Impossible de classer {entry.path.name} en refus: {e}")
            entry.path = target
