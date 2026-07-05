from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime

@dataclass
class ControlResult:
    """Résultat de contrôle avec timestamp."""
    datetime: datetime
    wayNumber: Optional[int] = None
    temperature: Optional[float] = None

@dataclass
class ElectricalControlData:
    """Données de contrôle électrique."""
    continuity_test: float
    hv_voltage_test: float
    hv_intensity_loss_test: float
    insulation_test: float
    power_voltage_test: float
    power_intensity_test: float
    power_calc_intensity_test: float
    datetime: datetime

@dataclass
class HeatControlData:
    """Données de contrôle thermique."""
    way_number: int
    temperature: float
    datetime: datetime

@dataclass
class ControlFrame:
    """Trame complète de contrôle reçue du banc."""
    frame_lines: tuple
    timestamp: datetime
    control_type: str
    data: dict

    def to_dict(self):
        return asdict(self)

class DataParser:
    """Parse les données brutes du banc de contrôle."""

    ELECTRICAL_CONTROL_MIN_LENGTH = 13
    HEAT_CONTROL_MAX_LENGTH = 12

    @staticmethod
    def parse_electrical_control(frame: tuple) -> Optional[ElectricalControlData]:
        """Parse une trame de contrôle électrique."""
        if len(frame) != 2:
            return None

        try:
            line1 = frame[0]
            line2 = frame[1]

            # Le contrôle électrique a des données spécifiques
            if len(line2) < DataParser.ELECTRICAL_CONTROL_MIN_LENGTH:
                return None

            # Extraction des valeurs numériques
            values = [float(v) for v in line2]

            return ElectricalControlData(
                continuity_test=values[0],
                hv_voltage_test=values[1],
                hv_intensity_loss_test=values[2],
                insulation_test=values[3],
                power_voltage_test=values[4],
                power_intensity_test=values[5],
                power_calc_intensity_test=values[6],
                datetime=datetime.now()
            )
        except (ValueError, IndexError) as e:
            return None

    @staticmethod
    def parse_heat_control(frame: tuple) -> Optional[List[HeatControlData]]:
        """Parse une trame de contrôle thermique."""
        if len(frame) != 2:
            return None

        try:
            line1 = frame[0]
            line2 = frame[1]

            # Le contrôle thermique a au maximum 12 valeurs par voie
            if len(line2) >= DataParser.ELECTRICAL_CONTROL_MIN_LENGTH:
                return None

            # Chaque valeur représente une température pour une voie
            results = []
            for way_number, temp_str in enumerate(line2, 1):
                temperature = float(temp_str)
                results.append(HeatControlData(
                    way_number=way_number,
                    temperature=temperature,
                    datetime=datetime.now()
                ))

            return results if results else None

        except (ValueError, IndexError):
            return None

    @staticmethod
    def classify_frame(frame: tuple) -> Optional[str]:
        """Détermine le type de contrôle basé sur la taille des données."""
        if len(frame) != 2:
            return None

        line2 = frame[1]
        if len(line2) < DataParser.ELECTRICAL_CONTROL_MIN_LENGTH:
            return 'electrical'
        else:
            return 'heat'
