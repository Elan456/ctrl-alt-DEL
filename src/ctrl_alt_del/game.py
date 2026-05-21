from __future__ import annotations

import pygame

from ctrl_alt_del.crew import CrewMate, CrewRole
from ctrl_alt_del.del_ai import DEL
from ctrl_alt_del.ship import Ship
from ctrl_alt_del.systems import SystemKind, SystemState

SCREEN_SIZE = (960, 640)
ROOM_SIZE = 96
ROOM_MARGIN = 80


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("ctrl-alt-DEL Prototype")
        self.screen = pygame.display.set_mode(SCREEN_SIZE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)

        self.ship = Ship.prototype()
        self.sprites = pygame.sprite.Group()
        self.player = self._crew(
            "player",
            CrewRole.PLAYER_TECHNICIAN,
            "maintenance_corridor",
            (368, 432),
            (90, 200, 255),
            True,
        )
        self._crew("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (176, 432), (255, 190, 90))
        self._crew("ops", CrewRole.OPERATIONS_OFFICER, "bridge", (560, 144), (180, 230, 120))
        self._crew("sec", CrewRole.SECURITY_OFFICER, "security", (176, 144), (235, 110, 110))

        self.del_ai = DEL(self.ship)
        self.del_output = self.del_ai.execute("/status oxygen")

    def run(self) -> int:
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self._handle_key(event.key)

            self.ship.tick(dt)
            self._draw()

        pygame.quit()
        return 0

    def _crew(
        self,
        crew_id: str,
        role: CrewRole,
        room: str,
        position: tuple[int, int],
        color: tuple[int, int, int],
        is_player: bool = False,
    ) -> CrewMate:
        crew_member = CrewMate(crew_id, role, room, position, color, is_player)
        self.sprites.add(crew_member)
        self.ship.register_crew(crew_member)
        return crew_member

    def _handle_key(self, key: int) -> None:
        speed = 8
        if key in (pygame.K_w, pygame.K_UP):
            self.player.move_by(0, -speed)
        elif key in (pygame.K_s, pygame.K_DOWN):
            self.player.move_by(0, speed)
        elif key in (pygame.K_a, pygame.K_LEFT):
            self.player.move_by(-speed, 0)
        elif key in (pygame.K_d, pygame.K_RIGHT):
            self.player.move_by(speed, 0)
        elif key == pygame.K_1:
            self.ship.damage_system(SystemKind.POWER, actor="player")
            self.del_output = self.del_ai.execute("/status power")
        elif key == pygame.K_2:
            self.ship.damage_system(SystemKind.OXYGEN, actor="player")
            self.del_output = self.del_ai.execute("/status oxygen")
        elif key == pygame.K_3:
            self.ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")
            self.del_output = self.del_ai.execute("/status oxygen")
        elif key == pygame.K_4:
            self.del_output = self.del_ai.execute("/task eng repair oxygen")
        elif key == pygame.K_5:
            self.del_output = self.del_ai.think()

    def _draw(self) -> None:
        self.screen.fill((10, 14, 20))
        self._draw_rooms()
        self.sprites.draw(self.screen)
        self._draw_hud()
        pygame.display.flip()

    def _draw_rooms(self) -> None:
        for room in self.ship.rooms.values():
            x = ROOM_MARGIN + room.grid_position[0] * ROOM_SIZE
            y = ROOM_MARGIN + room.grid_position[1] * ROOM_SIZE
            rect = pygame.Rect(x, y, ROOM_SIZE - 10, ROOM_SIZE - 10)
            pygame.draw.rect(self.screen, (34, 45, 58), rect)
            pygame.draw.rect(self.screen, (80, 98, 118), rect, 2)
            label = self.font.render(room.name.replace("_", " "), True, (210, 220, 230))
            self.screen.blit(label, (x + 8, y + 8))

    def _draw_hud(self) -> None:
        y = 12
        lines = [
            "WASD/arrows move. 1 damage power. 2 damage oxygen. 3 spoof oxygen. 4 task engineer. 5 DEL think.",
            f"Arrival: {self.ship.arrival_seconds_remaining:05.1f}s",
            f"DEL: {self.del_output}",
        ]
        for line in lines:
            surface = self.font.render(line, True, (230, 235, 240))
            self.screen.blit(surface, (12, y))
            y += 24
