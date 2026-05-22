from __future__ import annotations

import pygame

from ctrl_alt_del.crew import CrewMate, CrewRole
from ctrl_alt_del.del_ai import DEL, TranscriptSink
from ctrl_alt_del.ship import Ship
from ctrl_alt_del.systems import SystemKind, SystemState

SCREEN_SIZE = (960, 640)
PLAYER_SPEED = 180
PLAYER_COLLISION_INSET = 3
MACHINE_PANEL_WIDTH = 300
MACHINE_BUTTON_HEIGHT = 30
BUTTON_HIGHLIGHT_SECONDS = 0.35
TOAST_SECONDS = 2.4
CREW_TASK_LABEL_MAX_WIDTH = 150
CREW_TASK_LABEL_PADDING_X = 5
CREW_TASK_LABEL_PADDING_Y = 3


class Game:
    def __init__(self, del_transcript: TranscriptSink | None = None) -> None:
        pygame.init()
        pygame.display.set_caption("ctrl-alt-DEL Prototype")
        self.screen = pygame.display.set_mode(SCREEN_SIZE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.small_font = pygame.font.Font(None, 20)
        self._machine_buttons: list[tuple[pygame.Rect, SystemKind, str]] = []
        self._selected_button: tuple[SystemKind, str] | None = None
        self._button_highlight_remaining = 0.0
        self._toast_message = ""
        self._toast_remaining = 0.0

        self.ship = Ship.prototype()
        self.sprites = pygame.sprite.Group()
        self.player = self._crew(
            "tec",
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
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self._handle_mouse_down(event.pos)

                with self.del_ai.lock:
                    self._move_player(dt)
                    self._update_crew_ai(dt)
                    self.ship.tick(dt)
                    self._update_feedback(dt)
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
                self.ship.damage_system(SystemKind.POWER, actor="tec")
            elif key == pygame.K_2:
                self.ship.damage_system(SystemKind.OXYGEN, actor="tec")
            elif key == pygame.K_3:
                self.ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="tec")
            elif key == pygame.K_6:
                self.ship.lock_door("door_life_support_aft_corridor", actor="tec")
            elif key == pygame.K_7:
                self.ship.unlock_door("door_life_support_aft_corridor", actor="tec")

    def _handle_mouse_down(self, position: tuple[int, int]) -> None:
        with self.del_ai.lock:
            for rect, system, action in self._machine_buttons:
                if not rect.collidepoint(position):
                    continue
                self._selected_button = (system, action)
                self._button_highlight_remaining = BUTTON_HIGHLIGHT_SECONDS
                if action == "inspect":
                    self.ship.record_physical_report(system, "tec")
                    completed_task = self._complete_player_task("inspect", system)
                    self._show_toast(self._machine_action_message(system, "inspect", completed_task))
                elif action == "damage":
                    self.ship.damage_system(system, actor="tec")
                    self._show_toast(self._machine_action_message(system, "damage", False))
                elif action == "repair":
                    self.ship.repair_system(system, actor="tec")
                    completed_task = self._complete_player_task("repair", system)
                    self._show_toast(self._machine_action_message(system, "repair", completed_task))
                elif action == "spoof":
                    self.ship.spoof_system(system, SystemState.NORMAL, actor="tec")
                    self._show_toast(self._machine_action_message(system, "spoof", False))
                break

    def _complete_player_task(self, action: str, system: SystemKind) -> bool:
        task = self.player.task
        if task is None:
            return False
        task_matches = task.target == system.value and (
            task.kind == action or (action == "repair" and task.kind == "reset")
        )
        if not task_matches:
            return False
        self.ship.record("tec", f"reports task complete: {task.kind} {task.target}", task.target)
        self.player.clear_task()
        return True

    def _machine_action_message(self, system: SystemKind, action: str, completed_task: bool) -> str:
        ship_system = self.ship.systems[system]
        prefix = system.value.capitalize()
        suffix = " DEL task complete." if completed_task else ""
        if action == "inspect":
            return (
                f"{prefix} inspected: physical {ship_system.physical_state.value}, "
                f"reported {ship_system.reported_state.value}.{suffix}"
            )
        if action == "damage":
            return f"{prefix} loosened: physical {ship_system.physical_state.value}."
        if action == "repair":
            return f"{prefix} repaired: now {ship_system.physical_state.value}.{suffix}"
        if action == "spoof":
            return f"{prefix} spoofed: reported {ship_system.reported_state.value}."
        return f"{prefix}: action complete."

    def _show_toast(self, message: str) -> None:
        self._toast_message = message
        self._toast_remaining = TOAST_SECONDS

    def _update_feedback(self, dt: float) -> None:
        if self._button_highlight_remaining > 0:
            self._button_highlight_remaining = max(0.0, self._button_highlight_remaining - dt)
            if self._button_highlight_remaining <= 0:
                self._selected_button = None
        if self._toast_remaining > 0:
            self._toast_remaining = max(0.0, self._toast_remaining - dt)
            if self._toast_remaining <= 0:
                self._toast_message = ""

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
            self.ship.set_crew_location_from_point("tec", self.player.rect.center)

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

    def _update_crew_ai(self, dt: float) -> None:
        for sprite in self.sprites:
            if isinstance(sprite, CrewMate):
                sprite.update_ai(dt, self.ship)

    def _draw(self) -> None:
        self.screen.fill((10, 14, 20))
        with self.del_ai.lock:
            camera = self._camera_offset()
            self._draw_ship(camera)
            self._draw_machines(camera)
            self._draw_crew(camera)
            self._draw_hud()
            self._draw_machine_panel()
            self._draw_toast()
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

    def _draw_machines(self, camera: pygame.Vector2) -> None:
        nearby_machine = self.ship.nearby_machine(self.player.rect.center)
        for machine in self.ship.machines.values():
            rect = self._world_to_screen_rect(machine.rect, camera)
            system = self.ship.systems[machine.system]
            color = self._system_color(system.reported_state)
            if system.has_report_mismatch:
                color = (150, 120, 220)
            pygame.draw.rect(self.screen, color, rect, border_radius=3)
            border = (235, 240, 245) if machine == nearby_machine else (18, 24, 32)
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=3)
            label = self.small_font.render(machine.system.value.upper(), True, (235, 240, 245))
            label_rect = label.get_rect(center=rect.center)
            self.screen.blit(label, label_rect)

    def _draw_crew(self, camera: pygame.Vector2) -> None:
        for sprite in self.sprites:
            screen_rect = sprite.rect.move(-round(camera.x), -round(camera.y))
            self.screen.blit(sprite.image, screen_rect)
            if isinstance(sprite, CrewMate):
                self._draw_crew_task_label(sprite, screen_rect)

    def _draw_crew_task_label(self, crew_member: CrewMate, crew_rect: pygame.Rect) -> None:
        screen_bounds = self.screen.get_rect()
        if not crew_rect.colliderect(screen_bounds):
            return

        text = self._crew_task_label(crew_member)
        text = self._ellipsize_text(text, self.small_font, CREW_TASK_LABEL_MAX_WIDTH)
        color = (235, 240, 245) if crew_member.task is not None else (170, 182, 192)
        surface = self.small_font.render(text, True, color)
        label = surface.get_rect()
        label.width += CREW_TASK_LABEL_PADDING_X * 2
        label.height += CREW_TASK_LABEL_PADDING_Y * 2
        label.centerx = crew_rect.centerx
        label.bottom = crew_rect.top - 5
        label.clamp_ip(screen_bounds)

        fill = (18, 24, 32) if crew_member.task is not None else (16, 20, 26)
        border = (100, 132, 156) if crew_member.task is not None else (58, 70, 82)
        pygame.draw.rect(self.screen, fill, label, border_radius=4)
        pygame.draw.rect(self.screen, border, label, 1, border_radius=4)
        self.screen.blit(surface, surface.get_rect(center=label.center))

    def _draw_hud(self) -> None:
        y = 12
        lines = [
            f"FPS: {self.clock.get_fps():04.1f}",
            "WASD/arrows move. 1 damage power. 2 damage oxygen. 3 spoof oxygen. 6/7 player lock/unlock LS door.",
            self._arrival_hud_text(),
            f"Location: {self.player.room}",
            f"DEL: {self.del_ai.last_output}",
        ]
        for line in lines:
            surface = self.font.render(line, True, (230, 235, 240))
            self.screen.blit(surface, (12, y))
            y += 24

    def _arrival_hud_text(self) -> str:
        if not self.ship.launched:
            return f"Arrival: awaiting DEL launch ({self.ship.arrival_seconds_remaining:05.1f}s)"
        return f"Arrival: {self.ship.arrival_seconds_remaining:05.1f}s"

    def _draw_machine_panel(self) -> None:
        self._machine_buttons = []
        machine = self.ship.nearby_machine(self.player.rect.center)
        if machine is None:
            return

        system = self.ship.systems[machine.system]
        panel = pygame.Rect(12, SCREEN_SIZE[1] - 174, MACHINE_PANEL_WIDTH, 156)
        pygame.draw.rect(self.screen, (18, 24, 32), panel, border_radius=6)
        pygame.draw.rect(self.screen, (84, 102, 122), panel, 2, border_radius=6)

        y = panel.y + 10
        title = self.font.render(machine.name, True, (235, 240, 245))
        self.screen.blit(title, (panel.x + 12, y))
        y += 28

        status_lines = [
            f"System: {machine.system.value}",
            f"Physical: {system.physical_state.value}",
            f"Reported: {system.reported_state.value}",
        ]
        for line in status_lines:
            surface = self.small_font.render(line, True, (210, 220, 230))
            self.screen.blit(surface, (panel.x + 12, y))
            y += 20

        buttons = [
            ("Inspect", "inspect"),
            ("Loosen", "damage"),
            ("Repair", "repair"),
            ("Spoof OK", "spoof"),
        ]
        button_y = panel.bottom - MACHINE_BUTTON_HEIGHT - 12
        button_width = 66
        gap = 6
        for index, (label, action) in enumerate(buttons):
            rect = pygame.Rect(
                panel.x + 12 + index * (button_width + gap),
                button_y,
                button_width,
                MACHINE_BUTTON_HEIGHT,
            )
            selected = (
                self._selected_button == (machine.system, action)
                and self._button_highlight_remaining > 0
            )
            fill = (74, 104, 126) if selected else (42, 56, 70)
            border = (235, 240, 245) if selected else (100, 124, 146)
            pygame.draw.rect(self.screen, fill, rect, border_radius=4)
            pygame.draw.rect(self.screen, border, rect, 2 if selected else 1, border_radius=4)
            text = self.small_font.render(label, True, (235, 240, 245))
            self.screen.blit(text, text.get_rect(center=rect.center))
            self._machine_buttons.append((rect, machine.system, action))

    def _draw_toast(self) -> None:
        if not self._toast_message or self._toast_remaining <= 0:
            return

        text = self.font.render(self._toast_message, True, (238, 244, 248))
        padding_x = 16
        padding_y = 10
        rect = pygame.Rect(
            0,
            0,
            min(text.get_width() + padding_x * 2, SCREEN_SIZE[0] - 32),
            text.get_height() + padding_y * 2,
        )
        rect.centerx = SCREEN_SIZE[0] // 2
        toast_bottom = (
            SCREEN_SIZE[1] - 190
            if self.ship.nearby_machine(self.player.rect.center)
            else SCREEN_SIZE[1] - 20
        )
        rect.bottom = toast_bottom
        pygame.draw.rect(self.screen, (20, 28, 36), rect, border_radius=6)
        pygame.draw.rect(self.screen, (120, 150, 170), rect, 1, border_radius=6)
        self.screen.blit(text, text.get_rect(center=rect.center))

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
        rects.extend(self._pygame_rect(rect) for rect in self.ship.machine_rects())
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

    @staticmethod
    def _crew_task_label(crew_member: CrewMate) -> str:
        task = crew_member.task
        if task is None:
            return "Idle"
        return Game._format_task_text(task.kind, task.target)

    @staticmethod
    def _ellipsize_text(text: str, font: pygame.font.Font, max_width: int) -> str:
        if font.size(text)[0] <= max_width:
            return text
        suffix = "..."
        available_width = max_width - font.size(suffix)[0]
        if available_width <= 0:
            return suffix
        clipped = ""
        for character in text:
            if font.size(clipped + character)[0] > available_width:
                break
            clipped += character
        return clipped.rstrip() + suffix

    @staticmethod
    def _format_task_text(kind: str, target: str) -> str:
        verb = {
            "inspect": "Inspect",
            "repair": "Repair",
            "reset": "Reset",
            "guard": "Guard",
            "escort": "Escort",
            "detain": "Detain",
        }.get(kind, kind.replace("_", " ").capitalize())
        return f"{verb} {target.replace('_', ' ')}"

    @staticmethod
    def _system_color(state: SystemState) -> tuple[int, int, int]:
        return {
            SystemState.NORMAL: (80, 150, 120),
            SystemState.DEGRADED: (190, 145, 70),
            SystemState.FAILED: (180, 75, 70),
            SystemState.LOCKED: (130, 115, 150),
            SystemState.UNDER_REPAIR: (70, 125, 175),
        }[state]
