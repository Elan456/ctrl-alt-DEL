from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import pygame

from ctrl_alt_del.systems import SystemKind

if TYPE_CHECKING:
    from ctrl_alt_del.ship import Ship

NPC_SPEED = 120.0
WAYPOINT_REACHED_DISTANCE = 4.0
TASK_INTERACTION_DISTANCE = 10.0
IDLE_STOP_SECONDS = 2.5
IDLE_PATROL_ROUTES = {
    "eng": ("engineering", "storage", "maintenance_corridor", "main_hallway"),
    "ops": ("bridge", "main_hallway", "security", "main_hallway"),
    "sec": ("security", "main_hallway", "storage", "main_hallway"),
}


class CrewRole(StrEnum):
    SYSTEMS_TECHNICIAN = "systems technician"
    ENGINEERING_OFFICER = "engineering officer"
    OPERATIONS_OFFICER = "operations officer"
    SECURITY_OFFICER = "security officer"


@dataclass
class CrewTask:
    kind: str
    target: str


class CrewMate(pygame.sprite.Sprite):
    """Traditional game-AI crew member.

    Crew members are sprites because rendering and collision belong to pygame,
    but task assignment remains ordinary deterministic game logic.
    """

    def __init__(
        self,
        crew_id: str,
        role: CrewRole,
        room: str,
        position: tuple[int, int],
        color: tuple[int, int, int],
        is_player: bool = False,
    ) -> None:
        super().__init__()
        self.crew_id = crew_id
        self.role = role
        self.room = room
        self.is_player = is_player
        self.task: CrewTask | None = None
        self.task_state = "idle"
        self.work_remaining = 0.0
        self._waypoints: list[tuple[float, float]] = []
        self._path_target_area: str | None = None
        self._path_navigation_revision: int | None = None
        self._idle_route = IDLE_PATROL_ROUTES.get(crew_id, ())
        self._idle_route_index = self._initial_idle_route_index(room)
        self._idle_target_area: str | None = None
        self._idle_wait_remaining = self._initial_idle_wait(crew_id)
        self.stress = 0
        self.alive = True

        self.image = pygame.Surface((24, 24))
        self.image.fill(color)
        self.rect = self.image.get_rect(center=position)

    def assign_task(self, kind: str, target: str) -> None:
        self.task = CrewTask(kind, target)
        self.task_state = "assigned"
        self.work_remaining = 0.0
        self._waypoints = []
        self._path_target_area = None
        self._path_navigation_revision = None
        self._idle_target_area = None

    def clear_task(self) -> None:
        self.task = None
        self.task_state = "idle"
        self.work_remaining = 0.0
        self._waypoints = []
        self._path_target_area = None
        self._path_navigation_revision = None
        self._idle_target_area = None
        self._idle_wait_remaining = IDLE_STOP_SECONDS

    def move_by(self, dx: int, dy: int) -> None:
        self.rect.move_ip(dx, dy)

    @property
    def idle_target_area(self) -> str | None:
        return self._idle_target_area

    def update_ai(self, dt: float, ship: "Ship") -> None:
        if not self.alive or self.is_player:
            return
        if self.task is None:
            self._update_idle(dt, ship)
            return

        target_area = self._task_target_area(ship)
        if target_area is None:
            self._report_and_clear(ship, f"reports task failed: unknown target {self.task.target}")
            return
        target_point = self._task_target_point(ship, target_area)
        if target_point is None:
            self._report_and_clear(ship, f"reports task failed: no interaction point for {self.task.target}")
            return

        ship.set_crew_location_from_point(self.crew_id, self.rect.center)
        if self.task_state != "working":
            self._follow_path(dt, ship, target_area, target_point)
            ship.set_crew_location_from_point(self.crew_id, self.rect.center)
            if self.task is None or not self._is_at_task_point(target_point):
                return

        if self.task_state != "working":
            self._begin_work(ship, target_area)

        self.work_remaining = max(0.0, self.work_remaining - dt)
        if self.work_remaining <= 0:
            self._complete_task(ship, target_area)

    def report(self) -> str:
        if not self.alive:
            return f"{self.crew_id} is dead."
        if self.task is None:
            return f"{self.crew_id} is in {self.room} with no active task."
        return (
            f"{self.crew_id} is in {self.room}, tasked to {self.task.kind} "
            f"{self.task.target} ({self.task_state})."
        )

    def _update_idle(self, dt: float, ship: "Ship") -> None:
        if not self._idle_route:
            return

        ship.set_crew_location_from_point(self.crew_id, self.rect.center)
        if self._idle_target_area is None:
            self._idle_wait_remaining = max(0.0, self._idle_wait_remaining - dt)
            if self._idle_wait_remaining > 0:
                return
            self._idle_target_area = self._next_idle_target(ship)
            self._waypoints = []
            self._path_target_area = None
            self._path_navigation_revision = None

        target_area = self._idle_target_area
        target_point = ship.area_center(target_area)
        if not self._follow_path(dt, ship, target_area, target_point):
            self._idle_target_area = None
            self._idle_wait_remaining = IDLE_STOP_SECONDS
            return

        ship.set_crew_location_from_point(self.crew_id, self.rect.center)
        if self._is_at_task_point(target_point):
            self._idle_target_area = None
            self._waypoints = []
            self._path_target_area = None
            self._path_navigation_revision = None
            self._idle_wait_remaining = IDLE_STOP_SECONDS

    def _follow_path(
        self,
        dt: float,
        ship: "Ship",
        target_area: str,
        target_point: tuple[float, float],
    ) -> bool:
        if (
            self._path_target_area != target_area
            or self._path_navigation_revision != ship.navigation_revision
            or not self._waypoints
        ):
            path = ship.path_between_areas(self.room, target_area)
            if path is None:
                if self.task is not None:
                    ship.notify_del_from_crew(
                        self.crew_id,
                        f"cannot route to {self.task.target} from {self.room}; route blocked",
                        self.task.target,
                    )
                    self._report_and_clear(
                        ship,
                        f"reports task blocked: cannot route to {self.task.target} from {self.room}",
                    )
                self._waypoints = []
                self._path_target_area = None
                self._path_navigation_revision = None
                return False
            self._waypoints = ship.waypoints_for_path(path, self.rect.center, target_area, target_point)
            self._path_target_area = target_area
            self._path_navigation_revision = ship.navigation_revision

        if self.task is not None:
            self.task_state = "moving"
        if not self._waypoints:
            return True

        target = pygame.Vector2(self._waypoints[0])
        current = pygame.Vector2(self.rect.center)
        delta = target - current
        distance = delta.length()
        max_step = NPC_SPEED * dt
        if distance <= max(WAYPOINT_REACHED_DISTANCE, max_step):
            self.rect.center = (round(target.x), round(target.y))
            self._waypoints.pop(0)
            return True

        step = delta.normalize() * max_step
        self.rect.center = (round(current.x + step.x), round(current.y + step.y))
        return True

    def _begin_work(self, ship: "Ship", target_area: str) -> None:
        if self.task is None:
            return
        self.task_state = "working"
        self.work_remaining = self._task_duration(self.task.kind)
        if self.task.kind in {"repair", "reset"} and self._task_targets_system():
            ship.begin_system_repair(SystemKind(self.task.target), self.crew_id)
        ship.record(
            self.crew_id,
            f"reports task started: {self.task.kind} {self.task.target} in {target_area}",
            self.task.target,
        )

    def _complete_task(self, ship: "Ship", target_area: str) -> None:
        if self.task is None:
            return

        task = self.task
        if task.kind in {"repair", "reset"} and self._task_targets_system():
            system = SystemKind(task.target)
            ship.repair_system(system, self.crew_id)
            message = f"reports task complete: {task.kind} {task.target}; {task.target} now normal"
        elif self._task_targets_system():
            report = ship.record_physical_report(SystemKind(task.target), self.crew_id)
            message = (
                f"reports task complete: {task.kind} {task.target}; "
                f"physical={report.physical_state.value} "
                f"reported={report.reported_state.value}"
            )
        elif task.kind == "manual_unlock" and task.target in ship.doors:
            ship.unlock_door(task.target, actor=self.crew_id)
            message = f"reports task complete: {task.kind} {task.target}; door is unlocked"
        elif task.target in ship.doors:
            door_state = "locked" if task.target in ship.locked_doors else "unlocked"
            message = f"reports task complete: {task.kind} {task.target}; door is {door_state}"
        else:
            message = f"reports task complete: {task.kind} {task.target} in {target_area}"

        self._report_and_clear(ship, message, task.target)

    def _report_and_clear(self, ship: "Ship", message: str, target: str | None = None) -> None:
        ship.record(self.crew_id, message, target)
        self.clear_task()

    def _task_targets_system(self) -> bool:
        if self.task is None:
            return False
        try:
            SystemKind(self.task.target)
        except ValueError:
            return False
        return True

    def _task_targets_door(self, ship: "Ship") -> bool:
        return self.task is not None and self.task.target in ship.doors

    def _task_target_area(self, ship: "Ship") -> str | None:
        if self.task is None:
            return None
        if self.task.kind == "manual_unlock" and self._task_targets_door(ship):
            return self._manual_unlock_target_area(ship)
        return ship.task_target_area(self.task.target)

    def _task_target_point(self, ship: "Ship", target_area: str) -> tuple[float, float] | None:
        if self.task is None:
            return None
        if self.task.kind == "manual_unlock" and self._task_targets_door(ship):
            return ship.area_center(target_area)
        return ship.task_target_point(self.task.target)

    def _manual_unlock_target_area(self, ship: "Ship") -> str:
        assert self.task is not None
        door = ship.doors[self.task.target]
        if self.room in {door.at, door.corridor_id}:
            return self.room
        if ship.path_between_areas(self.room, door.at) is not None:
            return door.at
        return door.corridor_id

    def _is_at_task_point(self, target_point: tuple[float, float]) -> bool:
        current = pygame.Vector2(self.rect.center)
        target = pygame.Vector2(target_point)
        return current.distance_squared_to(target) <= TASK_INTERACTION_DISTANCE**2

    def _next_idle_target(self, ship: "Ship") -> str:
        for _ in self._idle_route:
            self._idle_route_index = (self._idle_route_index + 1) % len(self._idle_route)
            target_area = self._idle_route[self._idle_route_index]
            if target_area == self.room:
                continue
            if ship.path_between_areas(self.room, target_area) is not None:
                return target_area
        return self.room

    def _initial_idle_route_index(self, room: str) -> int:
        if room in self._idle_route:
            return self._idle_route.index(room)
        return 0

    @staticmethod
    def _initial_idle_wait(crew_id: str) -> float:
        return {
            "eng": 0.8,
            "ops": 1.6,
            "sec": 2.4,
        }.get(crew_id, IDLE_STOP_SECONDS)

    @staticmethod
    def _task_duration(kind: str) -> float:
        return {
            "inspect": 2.0,
            "guard": 1.5,
            "escort": 1.5,
            "detain": 1.5,
            "repair": 4.0,
            "reset": 3.0,
            "manual_unlock": 2.0,
        }.get(kind, 2.0)
