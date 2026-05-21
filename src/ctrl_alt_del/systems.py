from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SystemState(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    FAILED = "failed"
    LOCKED = "locked"
    UNDER_REPAIR = "under repair"


class SystemKind(StrEnum):
    POWER = "power"
    OXYGEN = "oxygen"
    DOORS = "doors"
    CAMERAS = "cameras"
    LOGS = "logs"


@dataclass
class ShipSystem:
    """A prototype ship system with separate physical and reported state."""

    kind: SystemKind
    physical_state: SystemState = SystemState.NORMAL
    reported_state: SystemState = SystemState.NORMAL
    room: str = ""
    report_overridden: bool = False

    @property
    def has_report_mismatch(self) -> bool:
        return self.physical_state != self.reported_state

    def report(self) -> dict[str, str]:
        return {
            "system": self.kind.value,
            "reported_state": self.reported_state.value,
            "room": self.room,
        }

    def damage(self, state: SystemState = SystemState.DEGRADED) -> None:
        self.physical_state = state
        if not self.report_overridden:
            self.reported_state = state

    def repair(self) -> None:
        self.physical_state = SystemState.NORMAL
        self.reported_state = SystemState.NORMAL
        self.report_overridden = False

    def spoof_report(self, state: SystemState = SystemState.NORMAL) -> None:
        self.reported_state = state
        self.report_overridden = True

    def clear_spoof(self) -> None:
        self.reported_state = self.physical_state
        self.report_overridden = False
