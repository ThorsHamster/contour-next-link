from dataclasses import dataclass
from enum import Enum
from datetime import datetime


@dataclass
class MedtronicDataStatus(Enum):
    invalid = 0
    valid = 1


@dataclass
class MedtronicMeasurementData:
    bgl_value: int = 0
    trend: str = ""
    active_insulin: float = 0
    current_basal_rate: float = 0
    temporary_basal_percentage: int = 0
    battery_level: int = 0
    insulin_units_remaining: int = 0
    status: MedtronicDataStatus = MedtronicDataStatus.invalid
    timestamp: datetime = None
