"""Étiquettes SBPL (imprimantes SATO) et règle de décision d'impression.

Porté de keck1 ``PrintService`` : deux étiquettes par machine (code-barres + numéro
de série), imprimées uniquement si le dernier contrôle est OK. Le moment dépend du
programme : durée 0 → après le contrôle électrique, durée > 0 → après la chauffe.

Le référentiel des programmes (code → article, durée, libellés) vivait dans Oracle
(table ``Program`` + vue ``VW_XX_ETIQ_MAC_ELEC``). Il est porté ici par un fichier
JSON en attendant l'équivalent côté Open Prod.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.logger import setup_logger

logger = setup_logger(__name__)

BARCODE_TEMPLATE = 'barcode.sbpl'
SERIAL_TEMPLATE = 'serial_number.sbpl'
LABEL_ENCODING = 'latin-1'
MACHINE_REGISTRY_MAX_ENTRIES = 5000


def load_json(path: Path, default: Any) -> Any:
    """Charge un JSON édité à la main ; fichier absent ou illisible → ``default`` (avec log)."""
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        logger.error(f"Fichier {path} illisible, ignoré: {e}")
        return default


def write_json_atomic(path: Path, data: Any) -> None:
    """Écrit via un fichier temporaire puis renommage : jamais de JSON tronqué en cas de coupure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data), encoding='utf-8')
    os.replace(tmp, path)


@dataclass
class Program:
    code: int
    name: str
    product_code: str
    duration: int
    labels: Tuple[str, ...] = ()

    @property
    def needs_heat_control(self) -> bool:
        return self.duration > 0

    def label(self, index: int) -> str:
        return self.labels[index] if index < len(self.labels) else ''


class ProgramCatalog:
    """Référentiel des programmes, chargé depuis un JSON ``{"<code>": {...}}``."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._programs: Dict[int, Program] = {}
        self.reload()

    def reload(self) -> None:
        self._programs = {}
        raw = load_json(self.path, {})
        if not isinstance(raw, dict):
            logger.error(f"{self.path}: un objet JSON {{code: programme}} est attendu")
            return
        for code, item in raw.items():
            if not isinstance(item, dict) or not str(code).strip().isdigit():
                continue  # clés de commentaire, entrées mal formées
            try:
                self._programs[int(code)] = Program(
                    code=int(code),
                    name=str(item.get('name', '')),
                    product_code=str(item.get('product_code', '')),
                    duration=int(item.get('duration', 0)),
                    labels=tuple(str(x) for x in item.get('labels', [])),
                )
            except (TypeError, ValueError) as e:
                logger.error(f"{self.path}: programme {code} ignoré ({e})")

    def get(self, code: Optional[int]) -> Optional[Program]:
        return self._programs.get(code) if code is not None else None

    def __len__(self) -> int:
        return len(self._programs)


class MachineRegistry:
    """Mémorise le programme de chaque machine (n° de série → code programme).

    La trame de chauffe ne porte pas le programme : seul le contrôle électrique,
    qui la précède, le donne. keck1 le retrouvait en base ; ici un JSON local,
    borné aux dernières machines et écrit de façon atomique.
    """

    def __init__(self, path: Path, max_entries: int = MACHINE_REGISTRY_MAX_ENTRIES):
        self.path = Path(path)
        self.max_entries = max_entries
        self._machines: Dict[str, int] = {}
        raw = load_json(self.path, {})
        if isinstance(raw, dict):
            for serial_number, program in raw.items():
                try:
                    self._machines[str(serial_number)] = int(program)
                except (TypeError, ValueError):
                    continue

    def remember(self, serial_number: str, program_number: int) -> None:
        """Mémorise et persiste ; une erreur disque est loggée, jamais propagée."""
        if self._machines.get(serial_number) == program_number:
            return
        self._machines.pop(serial_number, None)
        self._machines[serial_number] = program_number
        while len(self._machines) > self.max_entries:
            self._machines.pop(next(iter(self._machines)))
        try:
            write_json_atomic(self.path, self._machines)
        except OSError as e:
            logger.error(f"Impossible d'enregistrer {self.path}: {e}")

    def program_number_for(self, serial_number: str) -> Optional[int]:
        return self._machines.get(serial_number)


class LabelBuilder:
    """Remplit les gabarits SBPL avec les données d'une machine."""

    def __init__(self, templates_dir: Path):
        self.templates_dir = Path(templates_dir)

    def _template(self, name: str) -> bytes:
        return (self.templates_dir / name).read_bytes()

    @staticmethod
    def _fill(content: bytes, values: Dict[str, Optional[str]]) -> bytes:
        """Remplace chaque marqueur partout où il apparaît dans le gabarit."""
        for needle, value in values.items():
            content = content.replace(needle.encode('ascii'), (value or '').encode(LABEL_ENCODING, errors='replace'))
        return content

    def barcode_label(self, serial_number: str, program: Program, now: Optional[datetime] = None) -> bytes:
        """Étiquette produit : n° de série en code-barres, année, libellés article."""
        return self._fill(self._template(BARCODE_TEMPLATE), {
            'NUMERO_OF': serial_number,
            'YEAR': (now or datetime.now()).strftime('%y'),
            'LIBELLE1': program.label(0),
            'LIBELLE2': program.label(1),
            'LIBELLE3': program.label(2),
        })

    def serial_number_label(self, serial_number: str, program: Program) -> bytes:
        """Étiquette numéro de série : code article + n° de série (code-barres et clair)."""
        return self._fill(self._template(SERIAL_TEMPLATE), {
            'NUMEROSERIECB': serial_number,
            'CODE': program.product_code,
        })


def should_print(control_type: str, control_ok: bool, program: Optional[Program]) -> bool:
    """Règle keck1 : contrôle OK et étape finale du programme atteinte."""
    if not control_ok or program is None:
        return False
    if control_type == 'electrical':
        return not program.needs_heat_control
    if control_type == 'heat':
        return program.needs_heat_control
    return False
