from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pygame


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
        self.stress = 0

        self.image = pygame.Surface((24, 24))
        self.image.fill(color)
        self.rect = self.image.get_rect(center=position)

    def assign_task(self, kind: str, target: str) -> None:
        self.task = CrewTask(kind, target)

    def clear_task(self) -> None:
        self.task = None

    def move_by(self, dx: int, dy: int) -> None:
        self.rect.move_ip(dx, dy)

    def report(self) -> str:
        if self.task is None:
            return f"{self.crew_id} is in {self.room} with no active task."
        return f"{self.crew_id} is in {self.room}, tasked to {self.task.kind} {self.task.target}."
