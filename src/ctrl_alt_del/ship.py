from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic

from ctrl_alt_del.systems import ShipSystem, SystemKind, SystemState


@dataclass(frozen=True)
class Room:
    name: str
    grid_position: tuple[int, int]


@dataclass
class EvidenceEvent:
    timestamp: float
    source: str
    message: str
    target: str | None = None


@dataclass
class Ship:
    """Owns authored rooms, prototype systems, evidence logs, and crew registry."""

    rooms: dict[str, Room] = field(default_factory=dict)
    systems: dict[SystemKind, ShipSystem] = field(default_factory=dict)
    crew: dict[str, object] = field(default_factory=dict)
    evidence: list[EvidenceEvent] = field(default_factory=list)
    locked_doors: set[str] = field(default_factory=set)
    arrival_seconds_remaining: float = 300.0

    @classmethod
    def prototype(cls) -> Ship:
        ship = cls()
        ship.rooms = {
            "bridge": Room("bridge", (5, 1)),
            "engineering": Room("engineering", (1, 4)),
            "life_support": Room("life_support", (5, 4)),
            "security": Room("security", (1, 1)),
            "storage": Room("storage", (3, 5)),
            "main_hallway": Room("main_hallway", (3, 3)),
            "maintenance_corridor": Room("maintenance_corridor", (3, 4)),
        }
        ship.systems = {
            SystemKind.POWER: ShipSystem(SystemKind.POWER, room="engineering"),
            SystemKind.OXYGEN: ShipSystem(SystemKind.OXYGEN, room="life_support"),
            SystemKind.DOORS: ShipSystem(SystemKind.DOORS, room="security"),
            SystemKind.CAMERAS: ShipSystem(SystemKind.CAMERAS, room="security"),
            SystemKind.LOGS: ShipSystem(SystemKind.LOGS, room="bridge"),
        }
        ship.record("system", "prototype ship initialized")
        return ship

    def tick(self, dt: float) -> None:
        self.arrival_seconds_remaining = max(0.0, self.arrival_seconds_remaining - dt)

    def register_crew(self, crew_member: object) -> None:
        crew_id = getattr(crew_member, "crew_id")
        self.crew[crew_id] = crew_member
        self.record("crew", f"{crew_id} registered", target=crew_id)

    def status(self, system_name: str) -> dict[str, str | bool]:
        system = self.systems[SystemKind(system_name)]
        return system.report()

    def damage_system(
        self,
        system: SystemKind,
        state: SystemState = SystemState.DEGRADED,
        actor: str = "unknown",
    ) -> None:
        self.systems[system].damage(state)
        self.record("system", f"{actor} changed {system.value} to {state.value}", system.value)

    def spoof_system(
        self,
        system: SystemKind,
        reported_state: SystemState = SystemState.NORMAL,
        actor: str = "unknown",
    ) -> None:
        self.systems[system].spoof_report(reported_state)
        self.record(
            "logs",
            f"{actor} changed reported {system.value} state to {reported_state.value}",
            system.value,
        )

    def repair_system(self, system: SystemKind, actor: str) -> None:
        self.systems[system].repair()
        self.record("repair", f"{actor} repaired {system.value}", system.value)

    def crew_location(self, crew_id: str) -> str:
        crew_member = self.crew[crew_id]
        return getattr(crew_member, "room")

    def lock_door(self, door_id: str, actor: str = "DEL") -> None:
        self.locked_doors.add(door_id)
        self.record("door", f"{actor} locked {door_id}", door_id)

    def unlock_door(self, door_id: str, actor: str = "DEL") -> None:
        self.locked_doors.discard(door_id)
        self.record("door", f"{actor} unlocked {door_id}", door_id)

    def logs_for(self, target: str | None = None) -> list[EvidenceEvent]:
        if target is None:
            return list(self.evidence)
        return [event for event in self.evidence if event.target == target or target in event.message]

    def record(self, source: str, message: str, target: str | None = None) -> None:
        self.evidence.append(EvidenceEvent(monotonic(), source, message, target))
