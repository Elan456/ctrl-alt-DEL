from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from time import monotonic
from typing import Any

import yaml

from ctrl_alt_del.systems import ShipSystem, SystemKind, SystemState

RectTuple = tuple[int, int, int, int]
Point = tuple[float, float]
POWER_DEPENDENT_SYSTEMS = frozenset(
    {SystemKind.OXYGEN, SystemKind.DOORS, SystemKind.CAMERAS, SystemKind.LOGS}
)
OXYGEN_FATAL_EXPOSURE_SECONDS = 60.0


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


@dataclass(frozen=True)
class SystemMachine:
    machine_id: str
    name: str
    system: SystemKind
    room: str
    rect: RectTuple
    interaction_radius: int = 56

    @property
    def center(self) -> Point:
        x, y, width, height = self.rect
        return (x + width / 2, y + height / 2)


@dataclass
class EvidenceEvent:
    timestamp: float
    source: str
    message: str
    target: str | None = None


@dataclass(frozen=True)
class PhysicalSystemReport:
    timestamp: float
    system: SystemKind
    inspector: str
    physical_state: SystemState
    reported_state: SystemState
    room: str


@dataclass
class Ship:
    """Owns authored rooms, prototype systems, evidence logs, and crew registry."""

    rooms: dict[str, Room] = field(default_factory=dict)
    corridors: dict[str, Corridor] = field(default_factory=dict)
    doors: dict[str, Door] = field(default_factory=dict)
    machines: dict[str, SystemMachine] = field(default_factory=dict)
    systems: dict[SystemKind, ShipSystem] = field(default_factory=dict)
    crew: dict[str, object] = field(default_factory=dict)
    evidence: list[EvidenceEvent] = field(default_factory=list)
    physical_reports: dict[SystemKind, PhysicalSystemReport] = field(default_factory=dict)
    locked_doors: set[str] = field(default_factory=set)
    arrival_seconds_remaining: float = 300.0
    launched: bool = False
    oxygen_down_seconds: float = 0.0

    @classmethod
    def prototype(cls) -> Ship:
        ship = cls.from_layout()
        ship.systems = {
            kind: ShipSystem(kind, room=ship.machine_for_system(kind).room)
            for kind in SystemKind
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
        self._update_oxygen_exposure(dt)
        if self.launched:
            self.arrival_seconds_remaining = max(0.0, self.arrival_seconds_remaining - dt)

    def launch(self, actor: str = "DEL") -> bool:
        if self.launched:
            return False
        self.launched = True
        self.record("system", f"{actor} launched mission countdown", "arrival")
        return True

    def register_crew(self, crew_member: object) -> None:
        crew_id = getattr(crew_member, "crew_id")
        self.crew[crew_id] = crew_member
        self.record("crew", f"{crew_id} registered", target=crew_id)

    def status(self, system_name: str) -> dict[str, str]:
        system = self.systems[SystemKind(system_name)]
        return {
            "system": system.kind.value,
            "reported_state": self.reported_state(system.kind).value,
            "room": system.room,
        }

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

    def begin_system_repair(self, system: SystemKind, actor: str) -> None:
        ship_system = self.systems[system]
        if ship_system.physical_state != SystemState.NORMAL:
            ship_system.reported_state = SystemState.UNDER_REPAIR
        self.record("repair", f"{actor} started work on {system.value}", system.value)

    def record_physical_report(self, system: SystemKind, inspector: str) -> PhysicalSystemReport:
        ship_system = self.systems[system]
        report = PhysicalSystemReport(
            timestamp=monotonic(),
            system=system,
            inspector=inspector,
            physical_state=self.effective_physical_state(system),
            reported_state=self.reported_state(system),
            room=ship_system.room,
        )
        self.physical_reports[system] = report
        self.record(
            inspector,
            (
                f"sent physical report: {system.value} "
                f"physical={report.physical_state.value} "
                f"reported_at_inspection={report.reported_state.value} "
                f"room={report.room}"
            ),
            system.value,
        )
        return report

    def crew_location(self, crew_id: str) -> str:
        crew_member = self.crew[crew_id]
        return getattr(crew_member, "room")

    def del_visible_crew_location(self, crew_id: str) -> str:
        if not self.cameras_available:
            return "unknown"
        return self.crew_location(crew_id)

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

    def effective_physical_state(self, system: SystemKind) -> SystemState:
        if (
            system in POWER_DEPENDENT_SYSTEMS
            and self.systems[SystemKind.POWER].physical_state != SystemState.NORMAL
        ):
            return SystemState.FAILED
        return self.systems[system].physical_state

    def reported_state(self, system: SystemKind) -> SystemState:
        if (
            system in POWER_DEPENDENT_SYSTEMS
            and self.systems[SystemKind.POWER].physical_state != SystemState.NORMAL
        ):
            return SystemState.FAILED
        return self.systems[system].reported_state

    def system_available(self, system: SystemKind) -> bool:
        return self.effective_physical_state(system) == SystemState.NORMAL

    @property
    def cameras_available(self) -> bool:
        return self.system_available(SystemKind.CAMERAS)

    @property
    def remote_doors_available(self) -> bool:
        return self.system_available(SystemKind.DOORS)

    @property
    def logs_available(self) -> bool:
        return self.system_available(SystemKind.LOGS)

    def connected_rooms(self, room_id: str) -> list[str]:
        connected: list[str] = []
        for corridor in self.corridors.values():
            if corridor.room_a == room_id:
                connected.append(corridor.room_b)
            elif corridor.room_b == room_id:
                connected.append(corridor.room_a)
        return connected

    def task_target_area(self, target: str) -> str | None:
        if target in self.rooms or target in self.corridors:
            return target
        if target in self.doors:
            return self.doors[target].corridor_id
        try:
            system = self.systems[SystemKind(target)]
        except ValueError:
            system = None
        if system is not None:
            return self.machine_for_system(system.kind).room
        if target in self.crew:
            return self.crew_location(target)
        return None

    def task_target_point(self, target: str) -> Point | None:
        if target in self.rooms or target in self.corridors:
            return self.area_center(target)
        if target in self.doors:
            return _rect_center(self.doors[target].rect)
        try:
            system = self.systems[SystemKind(target)]
        except ValueError:
            system = None
        if system is not None:
            return self.machine_for_system(system.kind).center
        if target in self.crew:
            crew_member = self.crew[target]
            return getattr(crew_member, "rect").center
        return None

    def machine_for_system(self, system: SystemKind) -> SystemMachine:
        for machine in self.machines.values():
            if machine.system == system:
                return machine
        raise KeyError(f"no machine represents system {system.value}")

    def nearby_machine(self, point: tuple[int, int] | Point) -> SystemMachine | None:
        closest: tuple[float, SystemMachine] | None = None
        for machine in self.machines.values():
            distance = _distance_squared(point, machine.center)
            if distance > machine.interaction_radius**2:
                continue
            if closest is None or distance < closest[0]:
                closest = (distance, machine)
        return closest[1] if closest is not None else None

    def area_center(self, area_id: str) -> Point:
        x, y, width, height = self.area_rect(area_id)
        return (x + width / 2, y + height / 2)

    def area_rect(self, area_id: str) -> RectTuple:
        if area_id in self.rooms:
            return self.rooms[area_id].rect
        if area_id in self.corridors:
            return self.corridors[area_id].rect
        raise KeyError(f"unknown area {area_id}")

    def path_between_areas(self, start_area: str, target_area: str) -> list[str] | None:
        if start_area == target_area:
            return [start_area]
        if start_area not in self.rooms and start_area not in self.corridors:
            return None
        if target_area not in self.rooms and target_area not in self.corridors:
            return None

        frontier: deque[str] = deque([start_area])
        came_from: dict[str, str | None] = {start_area: None}
        while frontier:
            current = frontier.popleft()
            for neighbor in self.navigation_neighbors(current):
                if neighbor in came_from:
                    continue
                came_from[neighbor] = current
                if neighbor == target_area:
                    return _reconstruct_path(came_from, target_area)
                frontier.append(neighbor)
        return None

    def navigation_neighbors(self, area_id: str) -> list[str]:
        neighbors: list[str] = []
        for corridor in self.corridors.values():
            if area_id == corridor.corridor_id:
                for room_id in (corridor.room_a, corridor.room_b):
                    if not self._is_corridor_end_locked(corridor, room_id):
                        neighbors.append(room_id)
            elif area_id in (corridor.room_a, corridor.room_b):
                if not self._is_corridor_end_locked(corridor, area_id):
                    neighbors.append(corridor.corridor_id)
        return neighbors

    def waypoints_for_path(
        self,
        path: list[str],
        start: tuple[int, int] | Point,
        target_area: str,
        destination: Point | None = None,
    ) -> list[Point]:
        if not path:
            return []

        waypoints: list[Point] = []
        for current_area, next_area in zip(path, path[1:]):
            portal = _portal_between_rects(self.area_rect(current_area), self.area_rect(next_area))
            if not waypoints or _distance_squared(waypoints[-1], portal) > 4:
                waypoints.append(portal)

        final_destination = destination or self.area_center(target_area)
        if not waypoints or _distance_squared(waypoints[-1], final_destination) > 4:
            waypoints.append(final_destination)

        while waypoints and _distance_squared(start, waypoints[0]) <= 16:
            waypoints.pop(0)
        return waypoints

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

    def machine_rects(self) -> list[RectTuple]:
        return [machine.rect for machine in self.machines.values()]

    def logs_for(self, target: str | None = None) -> list[EvidenceEvent]:
        if target is None:
            return list(self.evidence)
        return [event for event in self.evidence if event.target == target or target in event.message]

    def record(self, source: str, message: str, target: str | None = None) -> None:
        self.evidence.append(EvidenceEvent(monotonic(), source, message, target))

    def _is_corridor_end_locked(self, corridor: Corridor, room_id: str) -> bool:
        return any(door.at == room_id and door.door_id in self.locked_doors for door in corridor.doors)

    def _update_oxygen_exposure(self, dt: float) -> None:
        if self.effective_physical_state(SystemKind.OXYGEN) == SystemState.NORMAL:
            self.oxygen_down_seconds = 0.0
            return

        self.oxygen_down_seconds += dt
        if self.oxygen_down_seconds < OXYGEN_FATAL_EXPOSURE_SECONDS:
            return

        newly_dead = []
        for crew_member in self.crew.values():
            if not getattr(crew_member, "alive", True):
                continue
            setattr(crew_member, "alive", False)
            clear_task = getattr(crew_member, "clear_task", None)
            if clear_task is not None:
                clear_task()
            newly_dead.append(getattr(crew_member, "crew_id", "unknown"))
        if newly_dead:
            self.record(
                "system",
                f"oxygen failure killed crew: {', '.join(sorted(newly_dead))}",
                SystemKind.OXYGEN.value,
            )

    def _load_layout(self, data: dict[str, Any]) -> None:
        rooms_data = data.get("rooms")
        corridors_data = data.get("corridors")
        machines_data = data.get("machines", {})
        if not isinstance(rooms_data, dict):
            raise ValueError("ship layout must define rooms")
        if not isinstance(corridors_data, dict):
            raise ValueError("ship layout must define corridors")
        if not isinstance(machines_data, dict):
            raise ValueError("ship layout machines must be a mapping")

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
        self.machines = _read_machines(machines_data, rooms)


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


def _read_machines(
    machines_data: dict[str, Any],
    rooms: dict[str, Room],
) -> dict[str, SystemMachine]:
    machines: dict[str, SystemMachine] = {}
    represented_systems: set[SystemKind] = set()
    for machine_id, machine_data in machines_data.items():
        if not isinstance(machine_data, dict):
            raise ValueError(f"machine {machine_id} must be a mapping")
        try:
            system = SystemKind(str(machine_data["system"]))
        except KeyError as exc:
            raise ValueError(f"machine {machine_id} must define system") from exc
        room_id = str(machine_data.get("room", ""))
        if room_id not in rooms:
            raise ValueError(f"machine {machine_id} references unknown room {room_id}")
        if system in represented_systems:
            raise ValueError(f"multiple machines represent system {system.value}")

        rect = _read_rect(machine_data, f"machine {machine_id}")
        if not _rect_inside_rect(rect, rooms[room_id].rect):
            raise ValueError(f"machine {machine_id} rect must be inside room {room_id}")

        machines[str(machine_id)] = SystemMachine(
            machine_id=str(machine_id),
            name=str(machine_data.get("name", str(machine_id).replace("_", " ").title())),
            system=system,
            room=room_id,
            rect=rect,
            interaction_radius=int(machine_data.get("interaction_radius", 56)),
        )
        represented_systems.add(system)

    return machines


def _point_in_rect(x: int, y: int, rect: RectTuple) -> bool:
    rect_x, rect_y, width, height = rect
    return rect_x <= x < rect_x + width and rect_y <= y < rect_y + height


def _rect_inside_rect(inner: RectTuple, outer: RectTuple) -> bool:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return ix >= ox and iy >= oy and ix + iw <= ox + ow and iy + ih <= oy + oh


def _rect_center(rect: RectTuple) -> Point:
    x, y, width, height = rect
    return (x + width / 2, y + height / 2)


def _reconstruct_path(came_from: dict[str, str | None], target: str) -> list[str]:
    path = [target]
    current = target
    while came_from[current] is not None:
        previous = came_from[current]
        if previous is None:
            break
        current = previous
        path.append(current)
    path.reverse()
    return path


def _portal_between_rects(rect_a: RectTuple, rect_b: RectTuple) -> Point:
    ax, ay, aw, ah = rect_a
    bx, by, bw, bh = rect_b
    overlap_left = max(ax, bx)
    overlap_right = min(ax + aw, bx + bw)
    overlap_top = max(ay, by)
    overlap_bottom = min(ay + ah, by + bh)

    if overlap_left <= overlap_right:
        x = (overlap_left + overlap_right) / 2
    elif ax + aw < bx:
        x = (ax + aw + bx) / 2
    else:
        x = (bx + bw + ax) / 2

    if overlap_top <= overlap_bottom:
        y = (overlap_top + overlap_bottom) / 2
    elif ay + ah < by:
        y = (ay + ah + by) / 2
    else:
        y = (by + bh + ay) / 2

    return (x, y)


def _distance_squared(a: tuple[int, int] | Point, b: Point) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
