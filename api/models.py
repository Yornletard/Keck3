"""Parsing des trames du banc de contrôle D1118.

Protocole (source : keck1 ``MachineService::prepareElectricData`` / ``cutdataResult``,
trames réelles dans ``ApiController::testElectricalAction`` / ``testHeatAction``) :

- Une trame = deux lignes série. Ligne 1 : ``[date jj/mm/aaaa, heure hh:mm:ss]``.
- Chaque champ est un entier ASCII à zéros de tête, terminé par un octet NUL.
- Ligne 2 « électrique » (12 champs) : n° d'OF, n° dans l'OF, opérateur, programme,
  continuité, tension HT, perte d'intensité HT, isolement, tension puissance (×0.1),
  intensité (×0.001), intensité calculée (×0.001), code statut.
- Ligne 2 « chauffe » (40 champs) : 8 voies × ``[OF, n° dans l'OF, opérateur,
  température (×0.1), code statut]``. Une voie dont l'OF vaut 0 est vide.
- N° de série machine = ``F{OF}-{n° dans l'OF}`` ; n° d'OF = ``F{OF}``.
"""

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

STATUS_OK = 1

ELECTRICAL_FIELD_COUNT = 12
HEAT_WAY_COUNT = 8
HEAT_FIELDS_PER_WAY = 5
# Frontière historique (keckCapture) : moins de 13 champs = électrique, sinon chauffe.
ELECTRICAL_MAX_LENGTH = 13

_DATE_RE = re.compile(r'^\d{2}/\d{2}/\d{4}$')
_LEADING_INT_RE = re.compile(r'^\s*([+-]?\d+)')


def clean_field(value: str) -> str:
    """Retire octets NUL, retours chariot et espaces autour d'un champ."""
    return value.replace('\x00', '').strip()


def to_int(value: str) -> int:
    """Équivalent de ``intval()`` PHP : entier de tête, 0 si absent."""
    match = _LEADING_INT_RE.match(clean_field(value))
    return int(match.group(1)) if match else 0


def make_fab_order_number(fab_order: int) -> str:
    return f'F{fab_order}'


def make_serial_number(fab_order: int, number_in_order: int) -> str:
    return f'F{fab_order}-{number_in_order}'


def is_header_line(line: Sequence[str]) -> bool:
    """Vrai si la ligne est la ligne 1 d'une trame (date en premier champ)."""
    return bool(line) and bool(_DATE_RE.match(clean_field(line[0])))


def parse_header(line: Sequence[str]) -> Optional[datetime]:
    """Horodatage du banc à partir de la ligne 1. ``None`` si illisible."""
    if len(line) < 2:
        return None
    try:
        return datetime.strptime(
            f'{clean_field(line[0])} {clean_field(line[1])[:8]}',
            '%d/%m/%Y %H:%M:%S',
        )
    except ValueError:
        return None


@dataclass
class ControlData:
    """Base commune : identité de la machine, horodatage du banc et statut."""
    datetime: datetime
    fab_order_number: str
    serial_number: str
    operator_number: int
    status_code: int

    @property
    def is_ok(self) -> bool:
        return self.status_code == STATUS_OK

    def as_dict(self) -> Dict[str, Any]:
        """Tous les attributs exposables au mapping Open Prod (champs + dérivés)."""
        data = asdict(self)
        data['status_ok'] = self.is_ok
        return data


@dataclass
class ElectricalControlData(ControlData):
    """Un contrôle électrique complet pour une machine."""
    program_number: int
    continuity_test: float
    hv_voltage_test: float
    hv_intensity_loss_test: float
    insulation_test: float
    power_voltage_test: float
    power_intensity_test: float
    power_calc_intensity_test: float


@dataclass
class HeatControlData(ControlData):
    """Une mesure de chauffe pour une voie du banc (= une machine)."""
    way_number: int
    temperature: float


CONTROL_CLASSES: Dict[str, type] = {'electrical': ElectricalControlData, 'heat': HeatControlData}


def control_to_dict(control: ControlData) -> Dict[str, Any]:
    """Champs du contrôle, horodatage en ISO 8601 (pour la file locale)."""
    data = asdict(control)
    data['datetime'] = control.datetime.isoformat()
    return data


def control_from_dict(kind: str, data: Dict[str, Any]) -> ControlData:
    """Inverse de ``control_to_dict``. Lève ValueError/TypeError/KeyError si le contenu est invalide."""
    cls = CONTROL_CLASSES[kind]
    values = dict(data)
    values['datetime'] = datetime.fromisoformat(values['datetime'])
    return cls(**values)


class DataParser:
    """Parse les trames brutes du banc de contrôle."""

    @staticmethod
    def classify_frame(frame: Sequence[Sequence[str]]) -> Optional[str]:
        """'electrical' ou 'heat' selon la taille de la ligne 2, ``None`` si trame invalide."""
        if len(frame) != 2 or not frame[1]:
            return None
        return 'electrical' if len(frame[1]) < ELECTRICAL_MAX_LENGTH else 'heat'

    @staticmethod
    def parse_electrical_control(frame: Sequence[Sequence[str]]) -> Optional[ElectricalControlData]:
        if DataParser.classify_frame(frame) != 'electrical':
            return None
        line2 = frame[1]
        if len(line2) < ELECTRICAL_FIELD_COUNT:
            return None

        values = [to_int(v) for v in line2[:ELECTRICAL_FIELD_COUNT]]
        fab_order, number_in_order = values[0], values[1]
        if fab_order == 0:
            return None

        return ElectricalControlData(
            datetime=parse_header(frame[0]) or datetime.now(),
            fab_order_number=make_fab_order_number(fab_order),
            serial_number=make_serial_number(fab_order, number_in_order),
            operator_number=values[2],
            status_code=values[11],
            program_number=values[3],
            continuity_test=float(values[4]),
            hv_voltage_test=float(values[5]),
            hv_intensity_loss_test=float(values[6]),
            insulation_test=float(values[7]),
            power_voltage_test=round(values[8] * 0.1, 3),
            power_intensity_test=round(values[9] * 0.001, 3),
            power_calc_intensity_test=round(values[10] * 0.001, 3),
        )

    @staticmethod
    def parse_heat_control(frame: Sequence[Sequence[str]]) -> Optional[List[HeatControlData]]:
        """Liste des voies actives (OF non nul). Liste vide = trame valide sans machine."""
        if DataParser.classify_frame(frame) != 'heat':
            return None
        timestamp = parse_header(frame[0]) or datetime.now()
        values = [to_int(v) for v in frame[1]]

        results: List[HeatControlData] = []
        for way in range(HEAT_WAY_COUNT):
            start = way * HEAT_FIELDS_PER_WAY
            chunk = values[start:start + HEAT_FIELDS_PER_WAY]
            if len(chunk) < HEAT_FIELDS_PER_WAY or chunk[0] == 0:
                continue
            fab_order, number_in_order, operator, temperature, status = chunk
            results.append(HeatControlData(
                datetime=timestamp,
                fab_order_number=make_fab_order_number(fab_order),
                serial_number=make_serial_number(fab_order, number_in_order),
                operator_number=operator,
                status_code=status,
                way_number=way + 1,
                temperature=round(temperature * 0.1, 1),
            ))
        return results
