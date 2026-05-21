"""ctrl-alt-DEL prototype package."""

from ctrl_alt_del.crew import CrewMate, CrewRole
from ctrl_alt_del.del_ai import DEL
from ctrl_alt_del.ship import Ship
from ctrl_alt_del.systems import ShipSystem, SystemKind, SystemState

__all__ = [
    "CrewMate",
    "CrewRole",
    "DEL",
    "Ship",
    "ShipSystem",
    "SystemKind",
    "SystemState",
]
