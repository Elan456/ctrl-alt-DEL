from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from time import monotonic
from typing import Any

import yaml

from ctrl_alt_del.systems import ShipSystem, SystemKind, SystemState

RectTuple = tuple[int, int, int, int]


@dataclass(frozen=True)
class Room:
    room_id: str
    name: str
    rect: RectTuple


@dataclass(frozen=True)
class Door:
    door_id: str
    corridor_id: str
    at: str
    rect: RectTuple


@dataclass(frozen=True)
class Corridor:
    corridor_id: str
    room_a: str
    room_b: str
    rect: RectTuple
    doors: tuple[Door, ...] = ()


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
    corridors: dict[str, Corridor] = field(default_factory=dict)
    doors: dict[str, Door] = field(default_factory=dict)
    systems: dict[SystemKind, ShipSystem] = field(default_factory=dict)
    crew: dict[str, object] = field(default_factory=dict)
    evidence: list[EvidenceEvent] = field(default_factory=list)
    locked_doors: set[str] = field(default_factory=set)
    arrival_seconds_remaining: float = 300.0

    @classmethod
    def prototype(cls) -> Ship:
        ship = cls.from_layout()
        ship.systems = {
            SystemKind.POWER: ShipSystem(SystemKind.POWER, room="engineering"),
            SystemKind.OXYGEN: ShipSystem(SystemKind.OXYGEN, room="life_support"),
            SystemKind.DOORS: ShipSystem(SystemKind.DOORS, room="security"),
            SystemKind.CAMERAS: ShipSystem(SystemKind.CAMERAS, room="security"),
            SystemKind.LOGS: ShipSystem(SystemKind.LOGS, room="bridge"),
        }
        ship.record("system", "prototype ship initialized")
        return ship

    @classmethod
    def from_layout(cls, layout_path: str | Path | None = None) -> Ship:
        data = _load_layout_data(layout_path)
        ship = cls()
        ship._load_layout(data)
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

    def set_crew_location_from_point(self, crew_id: str, point: tuple[int, int]) -> None:
        area = self.area_at_point(point)
        if area is None:
            return
        setattr(self.crew[crew_id], "room", area)

    def lock_door(self, door_id: str, actor: str = "DEL") -> None:
        if door_id not in self.doors:
            raise KeyError(f"unknown door {door_id}")
        self.locked_doors.add(door_id)
        self.record("door", f"{actor} locked {door_id}", door_id)

    def unlock_door(self, door_id: str, actor: str = "DEL") -> None:
        if door_id not in self.doors:
            raise KeyError(f"unknown door {door_id}")
        self.locked_doors.discard(door_id)
        self.record("door", f"{actor} unlocked {door_id}", door_id)

    def connected_rooms(self, room_id: str) -> list[str]:
        connected: list[str] = []
        for corridor in self.corridors.values():
            if corridor.room_a == room_id:
                connected.append(corridor.room_b)
            elif corridor.room_b == room_id:
                connected.append(corridor.room_a)
        return connected

    def area_at_point(self, point: tuple[int, int]) -> str | None:
        x, y = point
        for room_id, room in self.rooms.items():
            if _point_in_rect(x, y, room.rect):
                return room_id
        for corridor_id, corridor in self.corridors.items():
            if _point_in_rect(x, y, corridor.rect):
                return corridor_id
        return None

    def walkable_rects(self) -> list[RectTuple]:
        return [room.rect for room in self.rooms.values()] + [
            corridor.rect for corridor in self.corridors.values()
        ]

    def locked_door_rects(self) -> list[RectTuple]:
        return [self.doors[door_id].rect for door_id in self.locked_doors if door_id in self.doors]

    def logs_for(self, target: str | None = None) -> list[EvidenceEvent]:
        if target is None:
            return list(self.evidence)
        return [event for event in self.evidence if event.target == target or target in event.message]

    def record(self, source: str, message: str, target: str | None = None) -> None:
        self.evidence.append(EvidenceEvent(monotonic(), source, message, target))

    def _load_layout(self, data: dict[str, Any]) -> None:
        rooms_data = data.get("rooms")
        corridors_data = data.get("corridors")
        if not isinstance(rooms_data, dict):
            raise ValueError("ship layout must define rooms")
        if not isinstance(corridors_data, dict):
            raise ValueError("ship layout must define corridors")

        rooms: dict[str, Room] = {}
        for room_id, room_data in rooms_data.items():
            if not isinstance(room_data, dict):
                raise ValueError(f"room {room_id} must be a mapping")
            rooms[room_id] = Room(
                room_id=room_id,
                name=str(room_data.get("name", room_id.replace("_", " ").title())),
                rect=_read_rect(room_data, f"room {room_id}"),
            )

        corridors: dict[str, Corridor] = {}
        doors: dict[str, Door] = {}
        locked_doors: set[str] = set()
        for corridor_id, corridor_data in corridors_data.items():
            if not isinstance(corridor_data, dict):
                raise ValueError(f"corridor {corridor_id} must be a mapping")
            connects = corridor_data.get("connects")
            if not isinstance(connects, list) or len(connects) != 2:
                raise ValueError(f"corridor {corridor_id} must connect exactly two rooms")
            room_a, room_b = str(connects[0]), str(connects[1])
            for room_id in (room_a, room_b):
                if room_id not in rooms:
                    raise ValueError(f"corridor {corridor_id} references unknown room {room_id}")

            corridor_doors: list[Door] = []
            for door_data in corridor_data.get("doors", []):
                if not isinstance(door_data, dict):
                    raise ValueError(f"door in corridor {corridor_id} must be a mapping")
                door_id = str(door_data["id"])
                if door_id in doors:
                    raise ValueError(f"duplicate door id {door_id}")
                at = str(door_data["at"])
                if at not in (room_a, room_b):
                    raise ValueError(f"door {door_id} must be at one end of {corridor_id}")
                door = Door(
                    door_id=door_id,
                    corridor_id=corridor_id,
                    at=at,
                    rect=_read_rect(door_data, f"door {door_id}"),
                )
                doors[door_id] = door
                corridor_doors.append(door)
                if bool(door_data.get("locked", False)):
                    locked_doors.add(door_id)

            corridors[corridor_id] = Corridor(
                corridor_id=corridor_id,
                room_a=room_a,
                room_b=room_b,
                rect=_read_rect(corridor_data, f"corridor {corridor_id}"),
                doors=tuple(corridor_doors),
            )

        self.rooms = rooms
        self.corridors = corridors
        self.doors = doors
        self.locked_doors = locked_doors


def _load_layout_data(layout_path: str | Path | None) -> dict[str, Any]:
    if layout_path is None:
        raw = files("ctrl_alt_del.data").joinpath("default_ship.yaml").read_text()
    else:
        raw = Path(layout_path).read_text()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("ship layout must be a YAML mapping")
    return data


def _read_rect(data: dict[str, Any], label: str) -> RectTuple:
    rect = data.get("rect")
    if not isinstance(rect, list) or len(rect) != 4:
        raise ValueError(f"{label} must define rect as [x, y, width, height]")
    x, y, width, height = (int(value) for value in rect)
    if width <= 0 or height <= 0:
        raise ValueError(f"{label} rect width and height must be positive")
    return (x, y, width, height)


def _point_in_rect(x: int, y: int, rect: RectTuple) -> bool:
    rect_x, rect_y, width, height = rect
    return rect_x <= x < rect_x + width and rect_y <= y < rect_y + height
