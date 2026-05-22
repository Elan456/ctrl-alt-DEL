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
        self.stress = 0

        self.image = pygame.Surface((24, 24))
        self.image.fill(color)
        self.rect = self.image.get_rect(center=position)

    def assign_task(self, kind: str, target: str) -> None:
        self.task = CrewTask(kind, target)
        self.task_state = "assigned"
        self.work_remaining = 0.0
        self._waypoints = []
        self._path_target_area = None

    def clear_task(self) -> None:
        self.task = None
        self.task_state = "idle"
        self.work_remaining = 0.0
        self._waypoints = []
        self._path_target_area = None

    def move_by(self, dx: int, dy: int) -> None:
        self.rect.move_ip(dx, dy)

    def update_ai(self, dt: float, ship: "Ship") -> None:
        if self.is_player or self.task is None:
            return

        target_area = ship.task_target_area(self.task.target)
        if target_area is None:
            self._report_and_clear(ship, f"reports task failed: unknown target {self.task.target}")
            return
        target_point = ship.task_target_point(self.task.target)
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
        if self.task is None:
            return f"{self.crew_id} is in {self.room} with no active task."
        return (
            f"{self.crew_id} is in {self.room}, tasked to {self.task.kind} "
            f"{self.task.target} ({self.task_state})."
        )

    def _follow_path(
        self,
        dt: float,
        ship: "Ship",
        target_area: str,
        target_point: tuple[float, float],
    ) -> None:
        if self._path_target_area != target_area or not self._waypoints:
            path = ship.path_between_areas(self.room, target_area)
            if path is None:
                self._report_and_clear(
                    ship,
                    f"reports task blocked: cannot route to {self.task.target} from {self.room}",
                )
                return
            self._waypoints = ship.waypoints_for_path(path, self.rect.center, target_area, target_point)
            self._path_target_area = target_area

        self.task_state = "moving"
        if not self._waypoints:
            return

        target = pygame.Vector2(self._waypoints[0])
        current = pygame.Vector2(self.rect.center)
        delta = target - current
        distance = delta.length()
        max_step = NPC_SPEED * dt
        if distance <= max(WAYPOINT_REACHED_DISTANCE, max_step):
            self.rect.center = (round(target.x), round(target.y))
            self._waypoints.pop(0)
            return

        step = delta.normalize() * max_step
        self.rect.center = (round(current.x + step.x), round(current.y + step.y))

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

    def _is_at_task_point(self, target_point: tuple[float, float]) -> bool:
        current = pygame.Vector2(self.rect.center)
        target = pygame.Vector2(target_point)
        return current.distance_squared_to(target) <= TASK_INTERACTION_DISTANCE**2

    @staticmethod
    def _task_duration(kind: str) -> float:
        return {
            "inspect": 2.0,
            "guard": 1.5,
            "escort": 1.5,
            "detain": 1.5,
            "repair": 4.0,
            "reset": 3.0,
        }.get(kind, 2.0)
