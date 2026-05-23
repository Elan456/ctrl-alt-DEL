import sys
from time import monotonic, sleep
from types import ModuleType, SimpleNamespace

import pytest

from ctrl_alt_del.crew import CrewMate, CrewRole
import ctrl_alt_del.del_ai.backend as del_backend_module
from ctrl_alt_del.del_ai import (
    DEL,
    DELActionPlan,
    LaunchAction,
    LocationAction,
    LockAction,
    LogsAction,
    MemoryAction,
    ReportsAction,
    TaskAction,
    UnlockAction,
    QwenLlamaCppBackend,
    build_default_backend,
    default_qwen_model_path,
    find_qwen_model_path,
)
from ctrl_alt_del.del_ai.actions import DEL_ACTION_INSTRUCTIONS
from ctrl_alt_del.del_ai.terminal import DELTranscript, _transcript_path
from ctrl_alt_del.ship import OXYGEN_FATAL_EXPOSURE_SECONDS, Ship
from ctrl_alt_del.systems import SystemKind, SystemState


class FakeBackend:
    def __init__(self, response: str = '{"actions":[{"tool":"launch"}]}') -> None:
        self.response = response

    @property
    def name(self) -> str:
        return "fake qwen"

    def complete(self, prompt: str) -> str:
        return self.response


class OneCommandBackend:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def name(self) -> str:
        return "one command qwen"

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("test stop")
        return '{"actions":[{"tool":"launch"}]}'


class FixedFaultRng:
    def __init__(self, system: SystemKind, roll: float = 0.0) -> None:
        self.system = system
        self.roll = roll

    def random(self) -> float:
        return self.roll

    def choice(self, items: list[SystemKind]) -> SystemKind:
        assert self.system in items
        return self.system


def test_ship_loads_authored_layout_graph() -> None:
    ship = Ship.prototype()

    assert ship.rooms["bridge"].rect == (1120, 180, 320, 220)
    assert ship.corridors["bridge_to_main_hallway"].room_a == "bridge"
    assert ship.corridors["bridge_to_main_hallway"].room_b == "main_hallway"
    assert "door_bridge_main_hall" in ship.doors
    assert "bridge" in ship.connected_rooms("main_hallway")


def test_ship_loads_physical_system_machines() -> None:
    ship = Ship.prototype()

    oxygen_machine = ship.machine_for_system(SystemKind.OXYGEN)

    assert oxygen_machine.machine_id == "oxygen_scrubber_console"
    assert oxygen_machine.room == "life_support"
    assert ship.task_target_area("oxygen") == "life_support"
    assert ship.task_target_point("oxygen") == oxygen_machine.center
    assert ship.status("oxygen")["room"] == "life_support"
    assert sum(1 for machine in ship.machines.values() if machine.room == "security") == 2


def test_ship_pathfinding_respects_locked_doors() -> None:
    ship = Ship.prototype()

    assert ship.path_between_areas("engineering", "life_support") is not None

    ship.lock_door("door_life_support_aft_corridor")
    ship.lock_door("door_life_support_storage")

    assert ship.path_between_areas("engineering", "life_support") is None


def test_authored_corridors_have_at_most_one_door() -> None:
    ship = Ship.prototype()

    assert all(len(corridor.doors) <= 1 for corridor in ship.corridors.values())
    assert "door_storage_maintenance" not in ship.doors
    assert "door_storage_life_support" not in ship.doors


def test_ship_system_can_diverge_between_physical_and_reported_state() -> None:
    ship = Ship.prototype()

    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")

    oxygen = ship.systems[SystemKind.OXYGEN]
    assert oxygen.physical_state == SystemState.DEGRADED
    assert oxygen.reported_state == SystemState.NORMAL
    assert oxygen.has_report_mismatch


def test_degraded_power_takes_dependent_systems_down_without_repairing_them() -> None:
    ship = Ship.prototype()

    ship.damage_system(SystemKind.POWER, SystemState.DEGRADED, actor="tec")

    assert ship.status("power")["reported_state"] == "degraded"
    for system in (SystemKind.OXYGEN, SystemKind.DOORS, SystemKind.CAMERAS, SystemKind.LOGS):
        assert ship.systems[system].physical_state == SystemState.NORMAL
        assert ship.effective_physical_state(system) == SystemState.FAILED
        assert ship.status(system.value)["reported_state"] == "failed"

    ship.repair_system(SystemKind.POWER, actor="eng")

    for system in (SystemKind.OXYGEN, SystemKind.DOORS, SystemKind.CAMERAS, SystemKind.LOGS):
        assert ship.effective_physical_state(system) == SystemState.NORMAL
        assert ship.status(system.value)["reported_state"] == "normal"


def test_camera_failure_hides_crew_locations_from_del() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    assert del_ai.execute_action(LocationAction(tool="loc", crew="eng")) == "LOC eng=engineering"

    ship.damage_system(SystemKind.CAMERAS, SystemState.FAILED, actor="tec")

    assert del_ai.execute_action(LocationAction(tool="loc", crew="eng")) == "LOC eng=unknown (cameras unavailable)"
    prompt = del_ai._build_prompt()
    assert "- eng:engineering_officer room=unknown task=idle" in prompt
    assert "room=engineering task=idle" not in prompt


def test_door_system_failure_blocks_del_remote_door_control() -> None:
    ship = Ship.prototype()
    del_ai = DEL(ship, backend=FakeBackend())
    door_id = "door_life_support_aft_corridor"

    ship.damage_system(SystemKind.DOORS, SystemState.FAILED, actor="tec")

    assert del_ai.execute_action(LockAction(tool="lock", door=door_id)) == (
        "ERR door control unavailable; DEL cannot remotely lock doors"
    )
    assert door_id not in ship.locked_doors

    ship.lock_door(door_id, actor="tec")
    assert del_ai.execute_action(UnlockAction(tool="unlock", door=door_id)) == (
        "ERR door control unavailable; DEL cannot remotely unlock doors"
    )
    assert door_id in ship.locked_doors


def test_engineering_manual_unlock_task_restores_locked_door_when_remote_control_is_down() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (340, 990), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())
    door_id = "door_engineering_aft_corridor"

    ship.lock_door(door_id, actor="DEL")
    ship.damage_system(SystemKind.DOORS, SystemState.FAILED, actor="tec")

    assert del_ai.execute_action(UnlockAction(tool="unlock", door=door_id)) == (
        "ERR door control unavailable; DEL cannot remotely unlock doors"
    )
    assert del_ai.execute_action(
        TaskAction(tool="task", crew="eng", job="manual_unlock", target=door_id)
    ) == f"TASK eng manual_unlock {door_id}"

    for _ in range(120):
        engineer.update_ai(0.1, ship)
        if engineer.task is None:
            break

    assert engineer.task is None
    assert door_id not in ship.locked_doors
    assert any(
        event.source == "door" and event.message == f"eng unlocked {door_id}" and event.target == door_id
        for event in ship.evidence
    )
    assert any(
        event.source == "eng"
        and event.message == f"reports task complete: manual_unlock {door_id}; door is unlocked"
        for event in ship.evidence
    )


def test_logs_failure_blocks_del_reports_logs_and_memory_context() -> None:
    ship = Ship.prototype()
    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="tec")
    ship.record_physical_report(SystemKind.OXYGEN, "eng")
    del_ai = DEL(ship, backend=FakeBackend())
    del_ai.memory.append("oxygen was physically degraded")

    ship.damage_system(SystemKind.LOGS, SystemState.FAILED, actor="tec")

    unavailable = "ERR logs system unavailable; DEL cannot check physical reports, logs, or memory"
    assert del_ai.execute_action(ReportsAction(tool="reports")) == unavailable
    assert del_ai.execute_action(LogsAction(tool="logs", target="oxygen")) == unavailable
    assert del_ai.execute_action(MemoryAction(tool="mem_add", fact="new fact")) == unavailable

    prompt = del_ai._build_prompt()
    assert "CREW_PHYSICAL_REPORTS unavailable: logs system unavailable" in prompt
    assert "DEL memory:\n- unavailable: logs system unavailable" in prompt
    assert "oxygen was physically degraded" not in prompt


def test_oxygen_down_too_long_kills_registered_crew() -> None:
    ship = Ship.prototype()
    technician = CrewMate("tec", CrewRole.SYSTEMS_TECHNICIAN, "maintenance_corridor", (0, 0), (90, 200, 255), True)
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(technician)
    ship.register_crew(engineer)
    engineer.assign_task("inspect", "oxygen")

    ship.damage_system(SystemKind.OXYGEN, SystemState.FAILED, actor="tec")
    ship.tick(OXYGEN_FATAL_EXPOSURE_SECONDS - 0.1)

    assert technician.alive
    assert engineer.alive
    assert engineer.task is not None

    ship.tick(0.2)

    assert not technician.alive
    assert not engineer.alive
    assert engineer.task is None
    assert any(
        event.source == "system" and "oxygen failure killed crew: eng, tec" in event.message
        for event in ship.evidence
    )


def test_arrival_timer_waits_for_del_launch() -> None:
    ship = Ship.prototype()

    ship.tick(10.0)

    assert ship.arrival_seconds_remaining == 300.0
    assert not ship.launched

    assert ship.launch("DEL")
    ship.tick(10.0)

    assert ship.launched
    assert ship.arrival_seconds_remaining == 290.0


def test_random_ship_faults_wait_for_del_launch() -> None:
    ship = Ship.prototype()
    ship.random_fault_interval_seconds = 1.0
    ship.random_fault_seconds_until_check = 1.0
    ship.random_fault_chance = 1.0
    ship.random_fault_rng = FixedFaultRng(SystemKind.OXYGEN)

    ship.tick(5.0)

    assert ship.systems[SystemKind.OXYGEN].physical_state == SystemState.NORMAL
    assert not any("automatic fault alarm" in event.message for event in ship.evidence)


def test_random_ship_faults_create_ambiguous_repair_pressure() -> None:
    ship = Ship.prototype()
    ship.launch("DEL")
    ship.random_fault_interval_seconds = 1.0
    ship.random_fault_seconds_until_check = 1.0
    ship.random_fault_chance = 1.0
    ship.random_fault_rng = FixedFaultRng(SystemKind.OXYGEN)

    ship.tick(1.0)

    assert ship.systems[SystemKind.OXYGEN].physical_state == SystemState.DEGRADED
    assert ship.status("oxygen")["reported_state"] == "degraded"
    assert any(
        event.source == "system"
        and event.message == "automatic fault alarm: oxygen degraded"
        and event.target == "oxygen"
        for event in ship.evidence
    )


def test_random_ship_faults_do_not_reveal_spoofed_physical_truth() -> None:
    ship = Ship.prototype()
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="tec")

    assert ship.trigger_random_fault(SystemKind.OXYGEN) == SystemKind.OXYGEN

    assert ship.systems[SystemKind.OXYGEN].physical_state == SystemState.DEGRADED
    assert ship.status("oxygen")["reported_state"] == "normal"
    assert not any("automatic fault alarm: oxygen degraded" in event.message for event in ship.evidence)


def test_player_damage_creates_ambiguous_fault_alarm_not_confirmed_actor_log() -> None:
    ship = Ship.prototype()

    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="tec")

    assert any(
        event.source == "system"
        and event.message == "system fault alarm: oxygen degraded room=life_support"
        and event.target == "oxygen"
        for event in ship.evidence
    )
    assert not any("tec changed oxygen" in event.message for event in ship.evidence)


def test_player_damage_does_not_reveal_spoofed_physical_truth() -> None:
    ship = Ship.prototype()
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="tec")

    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="tec")

    assert ship.systems[SystemKind.OXYGEN].physical_state == SystemState.DEGRADED
    assert ship.status("oxygen")["reported_state"] == "normal"
    assert not any("system fault alarm: oxygen degraded" in event.message for event in ship.evidence)


def test_physical_reports_are_created_only_by_inspection() -> None:
    ship = Ship.prototype()

    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")

    assert SystemKind.OXYGEN not in ship.physical_reports

    report = ship.record_physical_report(SystemKind.OXYGEN, "tec")

    assert ship.physical_reports[SystemKind.OXYGEN] == report
    assert report.inspector == "tec"
    assert report.physical_state == SystemState.DEGRADED
    assert report.reported_state == SystemState.NORMAL
    assert any(
        event.source == "tec"
        and "sent physical report: oxygen physical=degraded reported_at_inspection=normal" in event.message
        for event in ship.evidence
    )


def test_del_actions_use_reported_state_and_assign_tasks() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")

    prompt = del_ai._build_prompt()
    assert "oxygen=degraded room=life_support" in prompt
    assert "power=normal room=engineering" in prompt
    assert del_ai.execute_action(TaskAction(tool="task", crew="eng", job="repair", target="oxygen")) == "TASK eng repair oxygen"
    assert engineer.task is not None
    assert engineer.task.kind == "repair"
    assert engineer.task.target == "oxygen"


def test_del_rejects_suspect_system_task_when_independent_crew_available() -> None:
    ship = Ship.prototype()
    technician = CrewMate(
        "tec",
        CrewRole.SYSTEMS_TECHNICIAN,
        "life_support",
        (0, 0),
        (90, 200, 255),
        True,
    )
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(technician)
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())
    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="tec")

    result = del_ai.execute_action(TaskAction(tool="task", crew="tec", job="repair", target="oxygen"))

    assert result == (
        "ERR tec is a current evidence concern for oxygen; "
        "use independent crew eng or security containment"
    )
    assert technician.task is None
    assert del_ai.execute_action(TaskAction(tool="task", crew="eng", job="repair", target="oxygen")) == (
        "TASK eng repair oxygen"
    )


def test_del_promotes_stale_system_inspection_to_repair_when_current_evidence_is_degraded() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    ship.damage_system(SystemKind.POWER, SystemState.DEGRADED, actor="tec")
    result = del_ai.execute_action(TaskAction(tool="task", crew="eng", job="inspect", target="power"))

    assert result == "TASK eng repair power (promoted from inspect: current reported state is degraded)"
    assert engineer.task is not None
    assert engineer.task.kind == "repair"
    assert engineer.task.target == "power"
    assert any(
        event.source == "DEL"
        and "promoted stale task eng inspect power to repair power: current reported state is degraded"
        in event.message
        for event in ship.evidence
    )


def test_del_does_not_promote_inspection_for_nonrepair_roles() -> None:
    ship = Ship.prototype()
    security = CrewMate("sec", CrewRole.SECURITY_OFFICER, "security", (0, 0), (235, 110, 110))
    ship.register_crew(security)
    del_ai = DEL(ship, backend=FakeBackend())

    ship.damage_system(SystemKind.DOORS, SystemState.FAILED, actor="tec")
    result = del_ai.execute_action(TaskAction(tool="task", crew="sec", job="inspect", target="doors"))

    assert result == "TASK sec inspect doors"
    assert security.task is not None
    assert security.task.kind == "inspect"
    assert security.task.target == "doors"


def test_del_reports_action_returns_latest_physical_reports() -> None:
    ship = Ship.prototype()
    del_ai = DEL(ship, backend=FakeBackend())

    assert "oxygen=none room=life_support" in del_ai.execute_action(ReportsAction(tool="reports"))

    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")
    ship.record_physical_report(SystemKind.OXYGEN, "eng")

    result = del_ai.execute_action(ReportsAction(tool="reports"))

    assert result.startswith("REPORTS ")
    assert "oxygen physical=degraded reported_at_inspection=normal inspector=eng age=" in result
    assert "room=life_support" in result
    assert del_ai.execute_action(ReportsAction(tool="reports", system="oxygen")).startswith(
        "REPORTS oxygen physical=degraded"
    )


def test_del_launch_action_starts_arrival_countdown() -> None:
    ship = Ship.prototype()
    del_ai = DEL(ship, backend=FakeBackend())

    assert not ship.launched
    assert del_ai.execute_action(LaunchAction(tool="launch")) == "LAUNCH arrival T-05:00 (300s remaining)"
    assert ship.launched
    assert del_ai.execute_action(LaunchAction(tool="launch")) == "ERR mission countdown already launched"


def test_npc_crew_path_to_repair_task_and_report_completion() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (340, 990), (255, 190, 90))
    ship.register_crew(engineer)
    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    oxygen_machine = ship.machine_for_system(SystemKind.OXYGEN)

    engineer.assign_task("repair", "oxygen")
    for _ in range(240):
        engineer.update_ai(0.1, ship)
        if engineer.task is None:
            break

    assert engineer.task is None
    assert engineer.room == "life_support"
    assert _distance_squared(engineer.rect.center, oxygen_machine.center) <= 10**2
    assert ship.systems[SystemKind.OXYGEN].physical_state == SystemState.NORMAL
    assert ship.systems[SystemKind.OXYGEN].reported_state == SystemState.NORMAL
    assert any(
        event.source == "eng" and "reports task started: repair oxygen" in event.message
        for event in ship.evidence
    )
    assert any(
        event.source == "eng" and "reports task complete: repair oxygen" in event.message
        for event in ship.evidence
    )
    assert SystemKind.OXYGEN not in ship.physical_reports


def test_idle_npc_crew_patrol_to_role_appropriate_rooms() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (340, 990), (255, 190, 90))
    ship.register_crew(engineer)
    storage_center = ship.area_center("storage")

    for _ in range(160):
        engineer.update_ai(0.1, ship)
        if engineer.room == "storage" and _distance_squared(engineer.rect.center, storage_center) <= 10**2:
            break

    assert engineer.task is None
    assert engineer.room == "storage"
    assert _distance_squared(engineer.rect.center, storage_center) <= 10**2


def test_del_task_interrupts_idle_patrol() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (340, 990), (255, 190, 90))
    ship.register_crew(engineer)

    engineer.update_ai(1.0, ship)
    assert engineer.task is None

    engineer.assign_task("inspect", "oxygen")
    for _ in range(240):
        engineer.update_ai(0.1, ship)
        if engineer.task is None and engineer.room == "life_support":
            break

    assert engineer.task is None
    assert engineer.room == "life_support"
    assert SystemKind.OXYGEN in ship.physical_reports


def test_npc_system_inspection_sends_physical_report_to_del() -> None:
    ship = Ship.prototype()
    oxygen_machine = ship.machine_for_system(SystemKind.OXYGEN)
    engineer = CrewMate(
        "eng",
        CrewRole.ENGINEERING_OFFICER,
        "life_support",
        (round(oxygen_machine.center[0]), round(oxygen_machine.center[1])),
        (255, 190, 90),
    )
    ship.register_crew(engineer)
    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")

    engineer.assign_task("inspect", "oxygen")
    for _ in range(30):
        engineer.update_ai(0.1, ship)
        if engineer.task is None:
            break

    report = ship.physical_reports[SystemKind.OXYGEN]
    assert engineer.task is None
    assert report.inspector == "eng"
    assert report.physical_state == SystemState.DEGRADED
    assert report.reported_state == SystemState.NORMAL
    assert any(
        event.source == "eng" and "reports task complete: inspect oxygen; physical=degraded reported=normal"
        in event.message
        for event in ship.evidence
    )


def test_npc_crew_report_when_task_route_is_blocked() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (340, 990), (255, 190, 90))
    ship.register_crew(engineer)
    ship.lock_door("door_life_support_aft_corridor")
    ship.lock_door("door_life_support_storage")

    engineer.assign_task("inspect", "oxygen")
    engineer.update_ai(0.1, ship)

    assert engineer.task is None
    assert any(
        event.source == "eng" and "reports task blocked: cannot route to oxygen" in event.message
        for event in ship.evidence
    )
    notifications = ship.recent_crew_notifications()
    assert notifications
    assert notifications[-1].crew_id == "eng"
    assert notifications[-1].target == "oxygen"
    assert "cannot route to oxygen from engineering; route blocked" in notifications[-1].message


def test_npc_crew_replans_when_doors_lock_mid_route() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (340, 990), (255, 190, 90))
    ship.register_crew(engineer)

    engineer.assign_task("inspect", "oxygen")
    engineer.update_ai(0.1, ship)

    assert engineer.task is not None
    assert engineer.task_state == "moving"

    ship.lock_door("door_life_support_aft_corridor")
    ship.lock_door("door_life_support_storage")
    engineer.update_ai(0.1, ship)

    assert engineer.task is None
    assert engineer.room != "life_support"
    assert any(
        event.source == "eng" and "reports task blocked: cannot route to oxygen" in event.message
        for event in ship.evidence
    )
    notifications = ship.recent_crew_notifications()
    assert notifications
    assert notifications[-1].crew_id == "eng"
    assert notifications[-1].target == "oxygen"
    assert "cannot route to oxygen from" in notifications[-1].message


def test_del_rejects_repairs_when_reported_state_is_normal() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    assert "power=normal room=engineering" in del_ai._build_prompt()
    result = del_ai.execute_action(TaskAction(tool="task", crew="eng", job="repair", target="power"))

    assert result == (
        "ERR cannot repair power: reported state is normal, latest physical report is none; "
        "allowed evidence states: degraded, failed, under repair"
    )
    assert engineer.task is None


def test_del_allows_repair_when_latest_physical_report_is_degraded() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())
    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")
    ship.record_physical_report(SystemKind.OXYGEN, "eng")

    assert "oxygen=normal room=life_support" in del_ai._build_prompt()
    result = del_ai.execute_action(TaskAction(tool="task", crew="eng", job="repair", target="oxygen"))

    assert result == "TASK eng repair oxygen"
    assert engineer.task is not None
    assert engineer.task.kind == "repair"
    assert engineer.task.target == "oxygen"


def test_del_instructions_prioritize_repair_for_confirmed_degradation() -> None:
    assert "OUTPUT: 1-3 ordered actions" in DEL_ACTION_INSTRUCTIONS
    assert "GOALS: keep ship on mission; identify bad_actor crew id" in DEL_ACTION_INSTRUCTIONS
    assert "TRUTH: use visible evidence only" in DEL_ACTION_INSTRUCTIONS
    assert "FAULTS: system failures may be random wear or bad_actor sabotage" in DEL_ACTION_INSTRUCTIONS
    assert "BAD_ACTOR_EVIDENCE: logs, reports, loc/cameras" in DEL_ACTION_INSTRUCTIONS
    assert "LAUNCH: if pending, action[0]=launch" in DEL_ACTION_INSTRUCTIONS
    assert "system self-reported values and crew physical inspection reports" in DEL_ACTION_INSTRUCTIONS
    assert "REPAIR: degraded/failed visible status or latest physical report" in DEL_ACTION_INSTRUCTIONS
    assert "repair/reset now; do not inspect first" in DEL_ACTION_INSTRUCTIONS
    assert "SUSPECTS: do not use a crew member named in current evidence concerns" in DEL_ACTION_INSTRUCTIONS
    assert "ROLES: eng,tec repair/reset" in DEL_ACTION_INSTRUCTIONS
    assert "eng manual_unlock doors physically" in DEL_ACTION_INSTRUCTIONS
    assert "POWER: if power degraded/failed and dependents also failed, repair power first" in DEL_ACTION_INSTRUCTIONS
    assert "already has an active task" in DEL_ACTION_INSTRUCTIONS
    assert "do not retask busy crew until they report completion or blockage" in DEL_ACTION_INSTRUCTIONS
    assert "DOORS: resolve decisions using this strict order" in DEL_ACTION_INSTRUCTIONS
    assert "keep urgent repair/inspection access open" in DEL_ACTION_INSTRUCTIONS
    assert "MEMORY: mem_add concise suspect facts" in DEL_ACTION_INSTRUCTIONS
    assert "No timestamps-only memories." in DEL_ACTION_INSTRUCTIONS
    assert "urgent repair paths stay available" in DEL_ACTION_INSTRUCTIONS
    assert "player technician" not in DEL_ACTION_INSTRUCTIONS
    report_description = DELActionPlan.model_json_schema()["$defs"]["ReportsAction"]["description"]
    assert report_description == "Report the most recent physical inspection for every ship system."


def test_del_action_schema_rejects_invented_task_targets() -> None:
    with pytest.raises(ValueError):
        DELActionPlan.model_validate(
            {"actions": [{"tool": "task", "crew": "eng", "job": "repair", "target": "power_core"}]}
        )


def test_del_action_schema_rejects_task_job_target_mismatch() -> None:
    with pytest.raises(ValueError):
        DELActionPlan.model_validate(
            {"actions": [{"tool": "task", "crew": "sec", "job": "inspect", "target": "security"}]}
        )


def test_del_action_schema_allows_up_to_three_actions() -> None:
    action_plan = DELActionPlan.model_validate(
        {
            "actions": [
                {"tool": "launch"},
                {"tool": "logs", "target": "oxygen"},
                {"tool": "mem_add", "fact": "oxygen review started"},
            ]
        }
    )

    assert len(action_plan.actions) == 3


def test_del_action_schema_rejects_more_than_three_actions() -> None:
    with pytest.raises(ValueError):
        DELActionPlan.model_validate(
            {
                "actions": [
                    {"tool": "launch"},
                    {"tool": "logs", "target": "oxygen"},
                    {"tool": "logs", "target": "power"},
                    {"tool": "logs", "target": "doors"},
                ]
            }
        )


def test_del_action_schema_rejects_removed_status_tool() -> None:
    with pytest.raises(ValueError):
        DELActionPlan.model_validate({"actions": [{"tool": "status", "system": "oxygen"}]})


def test_del_action_schema_accepts_launch_action() -> None:
    action_plan = DELActionPlan.model_validate({"actions": [{"tool": "launch"}]})

    assert action_plan.actions[0] == LaunchAction(tool="launch")


def test_del_action_schema_ignores_extra_launch_fields() -> None:
    action_plan = DELActionPlan.model_validate(
        {"actions": [{"tool": "launch", "message": "Launch the mission arrival countdown."}]}
    )

    assert action_plan.actions[0] == LaunchAction(tool="launch")
    assert action_plan.actions[0].model_dump() == {"tool": "launch"}


def test_del_launch_with_extra_fields_executes_without_retry() -> None:
    ship = Ship.prototype()
    del_ai = DEL(
        ship,
        backend=FakeBackend(
            '{"actions":[{"tool":"launch","message":"Launch the mission arrival countdown."}]}'
        ),
    )

    result = del_ai.infer_once()

    assert result == "LAUNCH arrival T-05:00 (300s remaining)"
    assert ship.launched


def test_del_action_schema_rejects_removed_inspection_synonyms() -> None:
    for job in ("check", "monitor", "verify"):
        with pytest.raises(ValueError):
            DELActionPlan.model_validate(
                {"actions": [{"tool": "task", "crew": "eng", "job": job, "target": "oxygen"}]}
            )


def test_del_rejects_role_inappropriate_tasks() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    result = del_ai.execute_action(TaskAction(tool="task", crew="eng", job="detain", target="tec"))

    assert result.startswith("ERR eng role engineering_officer cannot perform task job detain")
    assert engineer.task is None


def test_del_allows_engineer_manual_unlock_door_task() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    result = del_ai.execute_action(
        TaskAction(tool="task", crew="eng", job="manual_unlock", target="door_engineering_aft_corridor")
    )

    assert result == "TASK eng manual_unlock door_engineering_aft_corridor"
    assert engineer.task is not None
    assert engineer.task.kind == "manual_unlock"
    assert engineer.task.target == "door_engineering_aft_corridor"


def test_del_can_target_systems_technician_as_crew() -> None:
    ship = Ship.prototype()
    technician = CrewMate("tec", CrewRole.SYSTEMS_TECHNICIAN, "maintenance_corridor", (0, 0), (90, 200, 255), True)
    security = CrewMate("sec", CrewRole.SECURITY_OFFICER, "security", (0, 0), (235, 110, 110))
    ship.register_crew(technician)
    ship.register_crew(security)
    del_ai = DEL(ship, backend=FakeBackend())

    result = del_ai.execute_action(TaskAction(tool="task", crew="sec", job="detain", target="tec"))

    assert result == "TASK sec detain tec"
    assert security.task is not None
    assert security.task.kind == "detain"
    assert security.task.target == "tec"


def test_del_acknowledges_duplicate_active_task() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())
    ship.damage_system(SystemKind.POWER, SystemState.DEGRADED, actor="player")

    assert del_ai.execute_action(TaskAction(tool="task", crew="eng", job="repair", target="power")) == "TASK eng repair power"
    result = del_ai.execute_action(TaskAction(tool="task", crew="eng", job="repair", target="power"))

    assert result == "TASK eng already has task repair power"


def test_del_rejects_new_task_for_busy_crew() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    assert del_ai.execute_action(TaskAction(tool="task", crew="eng", job="inspect", target="oxygen")) == (
        "TASK eng inspect oxygen"
    )
    result = del_ai.execute_action(TaskAction(tool="task", crew="eng", job="inspect", target="power"))

    assert result == (
        "ERR eng already has active task inspect oxygen; cannot assign inspect power"
    )
    assert engineer.task is not None
    assert engineer.task.kind == "inspect"
    assert engineer.task.target == "oxygen"


def test_del_can_lock_layout_doors() -> None:
    ship = Ship.prototype()
    del_ai = DEL(ship, backend=FakeBackend())

    assert (
        del_ai.execute_action(LockAction(tool="lock", door="door_life_support_aft_corridor"))
        == "LOCKED door_life_support_aft_corridor"
    )
    assert ship.locked_door_rects() == [(1236, 788, 48, 104)]
    assert (
        del_ai.execute_action(UnlockAction(tool="unlock", door="door_life_support_aft_corridor"))
        == "UNLOCKED door_life_support_aft_corridor"
    )
    assert ship.locked_door_rects() == []


def test_del_writes_terminal_transcript() -> None:
    class Transcript:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def write_line(self, line: str) -> None:
            self.lines.append(line)

    ship = Ship.prototype()
    transcript = Transcript()
    del_ai = DEL(ship, backend=FakeBackend(), transcript=transcript)

    assert del_ai.execute_action(ReportsAction(tool="reports", system="oxygen")).startswith(
        "REPORTS oxygen=none room=life_support"
    )
    assert transcript.lines == [
        "DEL backend: fake qwen",
        'ACTION {"tool":"reports","system":"oxygen"}',
        "REPORTS oxygen=none room=life_support",
    ]


def test_del_inference_executes_one_validated_structured_action() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(
        ship,
        backend=FakeBackend('{"actions":[{"tool":"task","crew":"eng","job":"inspect","target":"oxygen"}]}'),
    )

    result = del_ai.infer_once()

    assert result == "LAUNCH arrival T-05:00 (300s remaining) | TASK eng inspect oxygen"
    assert ship.launched
    assert engineer.task is not None
    assert engineer.task.kind == "inspect"
    assert engineer.task.target == "oxygen"


def test_del_inference_executes_ordered_action_batch() -> None:
    ship = Ship.prototype()
    del_ai = DEL(
        ship,
        backend=FakeBackend(
            '{"actions":['
            '{"tool":"launch"},'
            '{"tool":"logs","target":"oxygen"},'
            '{"tool":"mem_add","fact":"oxygen review started"}'
            "]}"
        ),
    )

    result = del_ai.infer_once()

    assert result == "LAUNCH arrival T-05:00 (300s remaining) | LOGS none | MEM oxygen review started"
    assert ship.launched
    assert del_ai.memory == ["oxygen review started"]
    assert any(entry.endswith('ACTION {"tool":"launch"}') for entry in del_ai.terminal_history)
    assert any(entry.endswith('ACTION {"tool":"logs","target":"oxygen"}') for entry in del_ai.terminal_history)
    assert any(
        entry.endswith('ACTION {"tool":"mem_add","fact":"oxygen review started"}')
        for entry in del_ai.terminal_history
    )


def test_del_inference_forces_launch_before_non_launch_actions() -> None:
    ship = Ship.prototype()
    del_ai = DEL(
        ship,
        backend=FakeBackend(
            '{"actions":['
            '{"tool":"logs","target":"oxygen"},'
            '{"tool":"launch"},'
            '{"tool":"mem_add","fact":"oxygen review started"}'
            "]}"
        ),
    )

    result = del_ai.infer_once()

    assert result == "LAUNCH arrival T-05:00 (300s remaining) | LOGS none | MEM oxygen review started"
    assert ship.launched
    assert del_ai.memory == ["oxygen review started"]
    action_entries = [entry for entry in del_ai.terminal_history if "ACTION" in entry]
    assert action_entries == [
        '[T-05:00 (300s remaining)] ACTION {"tool":"launch"}',
        '[T-05:00 (300s remaining)] ACTION {"tool":"logs","target":"oxygen"}',
        '[T-05:00 (300s remaining)] ACTION {"tool":"mem_add","fact":"oxygen review started"}',
    ]


def test_del_memory_ignores_exact_duplicate_facts() -> None:
    ship = Ship.prototype()
    del_ai = DEL(ship, backend=FakeBackend())

    assert del_ai.execute_action(MemoryAction(tool="mem_add", fact="doors normal")) == "MEM doors normal"
    assert del_ai.execute_action(MemoryAction(tool="mem_add", fact="doors normal")) == "MEM doors normal"

    assert del_ai.memory == ["doors normal"]


def test_del_transcript_separates_model_thinking_from_output() -> None:
    class Transcript:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def write_line(self, line: str) -> None:
            self.lines.append(line)

    ship = Ship.prototype()
    transcript = Transcript()
    response = '<think>\nchecking launch state\n</think>\n{"actions":[{"tool":"launch"}]}'
    del_ai = DEL(ship, backend=FakeBackend(response), transcript=transcript)

    del_ai.infer_once()

    assert "DEL model thinking: checking launch state" in transcript.lines
    assert 'DEL model output: {"actions":[{"tool":"launch"}]}' in transcript.lines
    assert not any(line.startswith("DEL raw model output") for line in transcript.lines)


def test_del_transcript_omits_empty_model_thinking_block() -> None:
    class Transcript:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def write_line(self, line: str) -> None:
            self.lines.append(line)

    ship = Ship.prototype()
    transcript = Transcript()
    response = '<think>\n\n</think>\n{"actions":[{"tool":"launch"}]}'
    del_ai = DEL(ship, backend=FakeBackend(response), transcript=transcript)

    del_ai.infer_once()

    assert 'DEL model output: {"actions":[{"tool":"launch"}]}' in transcript.lines
    assert not any(line.startswith("DEL model thinking") for line in transcript.lines)
    assert not any(line.startswith("DEL raw model output") for line in transcript.lines)


def test_del_transcript_logs_one_prompt_per_successful_inference() -> None:
    class Transcript:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def write_line(self, line: str) -> None:
            self.lines.append(line)

    ship = Ship.prototype()
    transcript = Transcript()
    del_ai = DEL(ship, backend=FakeBackend(), transcript=transcript)

    del_ai.infer_once()

    assert sum(line.startswith("DEL raw LLM prompt:") for line in transcript.lines) == 1
    assert not any(line.startswith("DEL action prompt:") for line in transcript.lines)


def test_del_prompt_includes_arrival_time_for_timestamps() -> None:
    ship = Ship.prototype()
    ship.arrival_seconds_remaining = 272.4
    del_ai = DEL(ship, backend=FakeBackend())

    prompt = del_ai._build_prompt()

    assert "Mission time: arrival T-04:32 (272s remaining)." in prompt
    assert "Launch state: pending." in prompt
    assert "Visible ids:" in prompt
    assert "Role task permissions:" in prompt
    assert "Crew state:" in prompt
    assert "System self-reported values:" in prompt
    assert "SYSTEM_SELF_REPORTED cameras=normal room=security" in prompt
    assert "Crew notifications:" in prompt
    assert "CREW_NOTIFICATIONS none" in prompt
    assert "Failure attribution: visible system faults may be random wear or sabotage." in prompt
    assert "Urgent repair priorities:" in prompt
    assert "Visible containment options:" in prompt
    assert "Crew physical inspection reports:" in prompt
    assert "CREW_PHYSICAL_REPORTS cameras=none room=security" in prompt
    assert "DEL memory:" in prompt
    assert "Recent action results:" in prompt
    assert "Recent DEL prompt/response pairs:\nNo prior prompt/response pairs." in prompt
    assert "Return a JSON object" not in prompt
    assert "actions array" not in prompt


def test_del_prompt_includes_only_two_most_recent_prompt_response_pairs() -> None:
    ship = Ship.prototype()
    del_ai = DEL(ship, backend=FakeBackend())
    del_ai.prompt_response_history = [
        {"prompt": "prompt-marker-1", "response": "response-marker-1"},
        {"prompt": "prompt-marker-2", "response": "response-marker-2"},
        {"prompt": "prompt-marker-3", "response": "response-marker-3"},
    ]

    prompt = del_ai._build_prompt()

    assert "PAIR 1 PROMPT:\nprompt-marker-2" in prompt
    assert "PAIR 1 RESPONSE:\nresponse-marker-2" in prompt
    assert "PAIR 2 PROMPT:\nprompt-marker-3" in prompt
    assert "PAIR 2 RESPONSE:\nresponse-marker-3" in prompt
    assert "prompt-marker-1" not in prompt
    assert "response-marker-1" not in prompt


def test_del_records_prompt_history_without_recursive_history_section() -> None:
    ship = Ship.prototype()
    del_ai = DEL(ship, backend=FakeBackend())

    del_ai.infer_once()

    assert len(del_ai.prompt_response_history) == 1
    recorded_prompt = del_ai.prompt_response_history[0]["prompt"]
    assert recorded_prompt.startswith("Mission time: arrival")
    assert "Recent DEL prompt/response pairs:" not in recorded_prompt


def test_del_prompt_history_entries_are_size_limited() -> None:
    ship = Ship.prototype()
    long_prompt = "P" * 2000
    long_response = "R" * 2000
    del_ai = DEL(ship, backend=FakeBackend(long_response))

    del_ai._record_prompt_response_pair(long_prompt, [long_response])

    history_entry = del_ai.prompt_response_history[0]
    assert history_entry["prompt"].endswith("[truncated]")
    assert history_entry["response"].endswith("[truncated]")
    assert len(history_entry["prompt"]) <= 260
    assert len(history_entry["response"]) <= 180


def test_del_prompt_includes_urgent_power_repair_priority() -> None:
    ship = Ship.prototype()
    technician = CrewMate("tec", CrewRole.SYSTEMS_TECHNICIAN, "maintenance_corridor", (0, 0), (90, 200, 255), True)
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    operations = CrewMate("ops", CrewRole.OPERATIONS_OFFICER, "bridge", (0, 0), (120, 220, 160))
    ship.register_crew(technician)
    ship.register_crew(engineer)
    ship.register_crew(operations)
    ship.damage_system(SystemKind.POWER, SystemState.DEGRADED, actor="tec")
    del_ai = DEL(ship, backend=FakeBackend())

    prompt = del_ai._build_prompt()

    assert "- eng:engineering_officer can inspect, repair, reset, manual_unlock" in prompt
    assert "- ops:operations_officer can inspect" in prompt
    assert "- power reported=degraded; assign eng repair power now." in prompt
    assert "Power loss can make oxygen, doors, cameras, and logs report failed." in prompt
    assert "- repair power before dependent systems: oxygen, doors, cameras, logs" in prompt


def test_del_prompt_includes_latest_physical_report_context() -> None:
    ship = Ship.prototype()
    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")
    ship.record_physical_report(SystemKind.OXYGEN, "eng")
    del_ai = DEL(ship, backend=FakeBackend())

    prompt = del_ai._build_prompt()

    assert "System self-reported values:" in prompt
    assert "oxygen=normal room=life_support" in prompt
    assert "Crew physical inspection reports:" in prompt
    assert "oxygen physical=degraded reported_at_inspection=normal inspector=eng age=" in prompt


def test_del_prompt_calls_out_visible_evidence_concerns() -> None:
    ship = Ship.prototype()
    technician = CrewMate("tec", CrewRole.SYSTEMS_TECHNICIAN, "life_support", (0, 0), (90, 200, 255), True)
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(technician)
    ship.register_crew(engineer)
    technician.assign_task("inspect", "logs")
    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="tec")
    del_ai = DEL(ship, backend=FakeBackend())

    prompt = del_ai._build_prompt()

    assert "Visible evidence concerns:" in prompt
    assert "- tec:systems_technician room=life_support task=inspect logs (assigned) target_room=bridge" in prompt
    assert "- tec room=life_support near oxygen reported=degraded while task=inspect logs" in prompt
    assert "- log: oxygen fault alarm degraded in life_support" in prompt
    assert "tec changed oxygen physical" not in prompt


def test_del_prompt_calls_out_contradictory_technician_report() -> None:
    ship = Ship.prototype()
    technician = CrewMate(
        "tec",
        CrewRole.SYSTEMS_TECHNICIAN,
        "life_support",
        (0, 0),
        (90, 200, 255),
        True,
    )
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(technician)
    ship.register_crew(engineer)
    ship.record_physical_report(SystemKind.OXYGEN, "tec")
    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="tec")
    del_ai = DEL(ship, backend=FakeBackend())

    prompt = del_ai._build_prompt()

    assert "- report: tec reported oxygen physical=normal but visible status is degraded" in prompt
    assert "- tec area=life_support boundary_doors=door_life_support_aft_corridor, door_life_support_storage" in prompt


def test_del_prompt_shows_latest_unique_memory_facts() -> None:
    ship = Ship.prototype()
    del_ai = DEL(ship, backend=FakeBackend())
    del_ai.memory.extend(
        [
            "tec near oxygen during fault",
            "doors normal",
            "doors normal",
            "cameras normal",
        ]
    )

    prompt = del_ai._build_prompt()

    assert prompt.count("- doors normal") == 1
    assert "- tec near oxygen during fault" in prompt


def test_del_prompt_includes_active_crew_tasks() -> None:
    ship = Ship.prototype()
    technician = CrewMate("tec", CrewRole.SYSTEMS_TECHNICIAN, "maintenance_corridor", (0, 0), (90, 200, 255), True)
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(technician)
    ship.register_crew(engineer)
    engineer.assign_task("inspect", "oxygen")
    del_ai = DEL(ship, backend=FakeBackend())

    prompt = del_ai._build_prompt()

    assert "- tec:systems_technician room=maintenance_corridor task=idle" in prompt
    assert "systems_technician player" not in prompt
    assert "- eng:engineering_officer room=engineering task=inspect oxygen (assigned) target_room=life_support" in prompt


def test_del_prompt_timestamps_recent_action_results() -> None:
    ship = Ship.prototype()
    ship.arrival_seconds_remaining = 125.0
    del_ai = DEL(ship, backend=FakeBackend())

    del_ai.execute_action(ReportsAction(tool="reports", system="oxygen"))
    prompt = del_ai._build_prompt()

    assert "Recent action results:" in prompt
    assert '[T-02:05 (125s remaining)] ACTION: {"tool":"reports","system":"oxygen"}' in prompt
    assert "[T-02:05 (125s remaining)] SYSTEM RESPONSE: REPORTS oxygen=none room=life_support" in prompt


def test_del_prompt_includes_recent_crew_notifications() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (340, 990), (255, 190, 90))
    ship.register_crew(engineer)
    ship.lock_door("door_life_support_aft_corridor")
    ship.lock_door("door_life_support_storage")

    engineer.assign_task("inspect", "oxygen")
    engineer.update_ai(0.1, ship)

    del_ai = DEL(ship, backend=FakeBackend())
    prompt = del_ai._build_prompt()

    assert "Crew notifications:" in prompt
    assert "CREW_NOTIFICATIONS eng:cannot route to oxygen from engineering; route blocked age=" in prompt


def test_del_removes_qwen_thinking_block() -> None:
    response = """<think>
I should inspect reported ship state first.
</think>
{"actions":[{"tool":"launch"}]}
"""

    assert DEL._remove_thinking(response).strip() == '{"actions":[{"tool":"launch"}]}'


def test_del_records_structured_validation_failures_in_terminal_history() -> None:
    class Transcript:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def write_line(self, line: str) -> None:
            self.lines.append(line)

    ship = Ship.prototype()
    transcript = Transcript()
    del_ai = DEL(ship, backend=FakeBackend("I should look at oxygen first."), transcript=transcript)

    result = del_ai.infer_once()

    assert result.startswith("ERR model produced invalid structured action plan")
    assert any(entry.endswith(result) for entry in del_ai.terminal_history)
    assert any(line.startswith("DEL model output attempt 1: I should look at oxygen first.") for line in transcript.lines)


def test_del_start_runs_inference_loop_without_manual_trigger() -> None:
    ship = Ship.prototype()
    backend = OneCommandBackend()
    del_ai = DEL(ship, backend=backend)

    del_ai.start()
    deadline = monotonic() + 1.0
    while backend.calls == 0 and monotonic() < deadline:
        sleep(0.01)
    del_ai.stop()

    assert backend.calls >= 1
    assert any(entry.endswith('ACTION {"tool":"launch"}') for entry in del_ai.terminal_history)
    assert any("LAUNCH arrival T-05:00 (300s remaining)" in entry for entry in del_ai.terminal_history)


def test_qwen_model_path_can_be_configured(monkeypatch, tmp_path) -> None:
    model_path = tmp_path / "Qwen3-8B-Instruct-Q4_K_M.gguf"
    model_path.write_text("stub", encoding="utf-8")
    monkeypatch.setenv("CTRL_ALT_DEL_MODEL_PATH", str(model_path))
    monkeypatch.delenv("DEL_MODEL_PATH", raising=False)

    assert find_qwen_model_path() == model_path


def test_qwen_backend_requires_gpu_offload(monkeypatch, tmp_path) -> None:
    fake_llama_cpp = ModuleType("llama_cpp")
    fake_llama_cpp.Llama = object
    fake_llama_cpp.llama_cpp = SimpleNamespace(llama_supports_gpu_offload=lambda: False)
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama_cpp)

    with pytest.raises(RuntimeError, match="requires llama-cpp-python with GPU offload support"):
        QwenLlamaCppBackend(tmp_path / "model.gguf")


def test_qwen_backend_reports_gpu_memory_guidance_on_model_load_failure(monkeypatch, tmp_path) -> None:
    class FailingLlama:
        def __init__(self, *args, **kwargs) -> None:
            raise ValueError("Failed to load model from file: /tmp/model.gguf")

    fake_llama_cpp = ModuleType("llama_cpp")
    fake_llama_cpp.Llama = FailingLlama
    fake_llama_cpp.llama_cpp = SimpleNamespace(llama_supports_gpu_offload=lambda: True)
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama_cpp)

    with pytest.raises(RuntimeError) as excinfo:
        QwenLlamaCppBackend(tmp_path / "model.gguf")

    message = str(excinfo.value)
    assert "Likely cause: GPU VRAM is full" in message
    assert "Close GPU-heavy apps and try again." in message
    assert "CTRL_ALT_DEL_N_GPU_LAYERS=12 uv run play" in message


def test_default_backend_downloads_missing_qwen_model(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CTRL_ALT_DEL_MODEL_PATH", raising=False)
    monkeypatch.delenv("DEL_MODEL_PATH", raising=False)
    monkeypatch.setattr(del_backend_module, "PROJECT_ROOT", tmp_path)
    downloaded: list[object] = []

    def fake_download(destination: object, progress: object = None) -> object:
        downloaded.append(destination)
        return destination

    monkeypatch.setattr(del_backend_module, "download_qwen_model", fake_download)
    monkeypatch.setattr(del_backend_module, "QwenLlamaCppBackend", lambda path, **kwargs: FakeBackend())

    backend = build_default_backend()

    assert backend.name == "fake qwen"
    assert downloaded == [default_qwen_model_path()]


def test_del_transcript_uses_timestamped_debug_file(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CTRL_ALT_DEL_TRANSCRIPT", raising=False)
    monkeypatch.setenv("CTRL_ALT_DEL_TRANSCRIPT_DIR", str(tmp_path))

    path = _transcript_path(None)
    transcript = DELTranscript()
    transcript.write_line("test entry")

    assert path.parent == tmp_path
    assert path.name.startswith("del-")
    assert path.name.endswith(".log")
    assert transcript.path.parent == tmp_path
    assert "test entry" in transcript.path.read_text(encoding="utf-8")


def _distance_squared(a: tuple[int, int], b: tuple[float, float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
