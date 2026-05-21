from __future__ import annotations

import pygame

from ctrl_alt_del.crew import CrewMate, CrewRole
from ctrl_alt_del.del_ai import DEL, TranscriptSink
from ctrl_alt_del.ship import Ship
from ctrl_alt_del.systems import SystemKind, SystemState

SCREEN_SIZE = (960, 640)
PLAYER_SPEED = 180
PLAYER_COLLISION_INSET = 3


class Game:
    def __init__(self, del_transcript: TranscriptSink | None = None) -> None:
        pygame.init()
        pygame.display.set_caption("ctrl-alt-DEL Prototype")
        self.screen = pygame.display.set_mode(SCREEN_SIZE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)

        self.ship = Ship.prototype()
        self.sprites = pygame.sprite.Group()
        self.player = self._crew(
            "player",
            CrewRole.SYSTEMS_TECHNICIAN,
            "maintenance_corridor",
            (930, 835),
            (90, 200, 255),
            True,
        )
        self._crew("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (340, 990), (255, 190, 90))
        self._crew("ops", CrewRole.OPERATIONS_OFFICER, "bridge", (1280, 290), (180, 230, 120))
        self._crew("sec", CrewRole.SECURITY_OFFICER, "security", (340, 340), (235, 110, 110))

        self.del_ai = DEL(self.ship, transcript=del_transcript)
        self.del_ai.start()

    def run(self) -> int:
        running = True
        try:
            while running:
                dt = self.clock.tick(60) / 1000.0
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        self._handle_key(event.key)

                with self.del_ai.lock:
                    self._move_player(dt)
                    self.ship.tick(dt)
                self._draw()
        finally:
            self.del_ai.stop()
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
        with self.del_ai.lock:
            if key == pygame.K_1:
                self.ship.damage_system(SystemKind.POWER, actor="player")
            elif key == pygame.K_2:
                self.ship.damage_system(SystemKind.OXYGEN, actor="player")
            elif key == pygame.K_3:
                self.ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")
            elif key == pygame.K_6:
                self.ship.lock_door("door_life_support_aft_corridor", actor="player")
            elif key == pygame.K_7:
                self.ship.unlock_door("door_life_support_aft_corridor", actor="player")

    def _move_player(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        dx = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])
        dy = int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP])
        if dx == 0 and dy == 0:
            return

        movement = pygame.Vector2(dx, dy)
        if movement.length_squared() > 0:
            movement = movement.normalize() * PLAYER_SPEED * dt
        self._move_player_axis(round(movement.x), 0)
        self._move_player_axis(0, round(movement.y))
        with self.del_ai.lock:
            self.ship.set_crew_location_from_point("player", self.player.rect.center)

    def _move_player_axis(self, dx: int, dy: int) -> None:
        if dx == 0 and dy == 0:
            return
        candidate = self.player.rect.move(dx, dy)
        if self._can_occupy(candidate):
            self.player.rect = candidate

    def _can_occupy(self, rect: pygame.Rect) -> bool:
        for door_rect in self.ship.locked_door_rects():
            if rect.colliderect(self._pygame_rect(door_rect)):
                return False

        inset_rect = rect.inflate(-PLAYER_COLLISION_INSET * 2, -PLAYER_COLLISION_INSET * 2)
        points = [
            inset_rect.topleft,
            inset_rect.topright,
            inset_rect.bottomleft,
            inset_rect.bottomright,
            inset_rect.center,
        ]
        walkable = [self._pygame_rect(walkable_rect) for walkable_rect in self.ship.walkable_rects()]
        return all(any(walkable_rect.collidepoint(point) for walkable_rect in walkable) for point in points)

    def _draw(self) -> None:
        self.screen.fill((10, 14, 20))
        with self.del_ai.lock:
            camera = self._camera_offset()
            self._draw_ship(camera)
            self._draw_crew(camera)
            self._draw_hud()
        pygame.display.flip()

    def _draw_ship(self, camera: pygame.Vector2) -> None:
        for corridor in self.ship.corridors.values():
            rect = self._world_to_screen_rect(corridor.rect, camera)
            pygame.draw.rect(self.screen, (27, 36, 46), rect)
            pygame.draw.rect(self.screen, (58, 75, 92), rect, 2)

        for room in self.ship.rooms.values():
            rect = self._world_to_screen_rect(room.rect, camera)
            pygame.draw.rect(self.screen, (34, 45, 58), rect)
            pygame.draw.rect(self.screen, (80, 98, 118), rect, 2)

        for door in self.ship.doors.values():
            rect = self._world_to_screen_rect(door.rect, camera)
            color = (170, 80, 70) if door.door_id in self.ship.locked_doors else (80, 135, 125)
            pygame.draw.rect(self.screen, color, rect)
            pygame.draw.rect(self.screen, (18, 24, 32), rect, 2)

        for room in self.ship.rooms.values():
            rect = self._world_to_screen_rect(room.rect, camera)
            label = self.font.render(room.name, True, (210, 220, 230))
            self.screen.blit(label, (rect.x + 8, rect.y + 8))

    def _draw_crew(self, camera: pygame.Vector2) -> None:
        for sprite in self.sprites:
            screen_rect = sprite.rect.move(-round(camera.x), -round(camera.y))
            self.screen.blit(sprite.image, screen_rect)

    def _draw_hud(self) -> None:
        y = 12
        lines = [
            f"FPS: {self.clock.get_fps():04.1f}",
            "WASD/arrows move. 1 damage power. 2 damage oxygen. 3 spoof oxygen. 6/7 player lock/unlock LS door.",
            f"Arrival: {self.ship.arrival_seconds_remaining:05.1f}s",
            f"Location: {self.player.room}",
            f"DEL: {self.del_ai.last_output}",
        ]
        for line in lines:
            surface = self.font.render(line, True, (230, 235, 240))
            self.screen.blit(surface, (12, y))
            y += 24

    @staticmethod
    def _pygame_rect(rect: tuple[int, int, int, int]) -> pygame.Rect:
        return pygame.Rect(rect)

    def _camera_offset(self) -> pygame.Vector2:
        world_bounds = self._world_bounds()
        offset = pygame.Vector2(
            self.player.rect.centerx - SCREEN_SIZE[0] / 2,
            self.player.rect.centery - SCREEN_SIZE[1] / 2,
        )
        max_x = max(0, world_bounds.right - SCREEN_SIZE[0])
        max_y = max(0, world_bounds.bottom - SCREEN_SIZE[1])
        offset.x = min(max(offset.x, world_bounds.left), max_x)
        offset.y = min(max(offset.y, world_bounds.top), max_y)
        return offset

    def _world_bounds(self) -> pygame.Rect:
        rects = [self._pygame_rect(rect) for rect in self.ship.walkable_rects()]
        rects.extend(self._pygame_rect(door.rect) for door in self.ship.doors.values())
        bounds = rects[0].copy()
        for rect in rects[1:]:
            bounds.union_ip(rect)
        bounds.inflate_ip(160, 160)
        return bounds

    def _world_to_screen_rect(
        self,
        rect: tuple[int, int, int, int],
        camera: pygame.Vector2,
    ) -> pygame.Rect:
        screen_rect = self._pygame_rect(rect)
        screen_rect.move_ip(-round(camera.x), -round(camera.y))
        return screen_rect
