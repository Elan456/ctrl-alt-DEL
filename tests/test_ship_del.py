from time import monotonic, sleep

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
    assert "REPORTS unavailable: logs system unavailable" in prompt
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
    assert "assign an idle repair-capable crew member to repair or reset it immediately" in DEL_ACTION_INSTRUCTIONS
    assert "do not inspect it first" in DEL_ACTION_INSTRUCTIONS
    assert "If the launch state is pending, issue launch as the first action" in DEL_ACTION_INSTRUCTIONS
    assert "Choose one to three ordered ship actions" in DEL_ACTION_INSTRUCTIONS


def test_del_action_schema_rejects_invented_task_targets() -> None:
    with pytest.raises(ValueError):
        DELActionPlan.model_validate(
            {"actions": [{"tool": "task", "crew": "eng", "job": "repair", "target": "power_core"}]}
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


def test_del_rejects_duplicate_active_task() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())
    ship.damage_system(SystemKind.POWER, SystemState.DEGRADED, actor="player")

    assert del_ai.execute_action(TaskAction(tool="task", crew="eng", job="repair", target="power")) == "TASK eng repair power"
    result = del_ai.execute_action(TaskAction(tool="task", crew="eng", job="repair", target="power"))

    assert result == "ERR eng already has active task repair power; wait for a report or choose a different crew member"


def test_del_rejects_assigning_new_task_to_busy_crew() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    assert del_ai.execute_action(TaskAction(tool="task", crew="eng", job="inspect", target="oxygen")) == (
        "TASK eng inspect oxygen"
    )
    result = del_ai.execute_action(TaskAction(tool="task", crew="eng", job="inspect", target="power"))

    assert result == "ERR eng already has active task inspect oxygen; wait for a report or choose a different crew member"
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

    assert result == "TASK eng inspect oxygen"
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


def test_del_transcript_includes_raw_model_thinking() -> None:
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

    assert (
        'DEL raw model output: <think>\nchecking launch state\n</think>\n{"actions":[{"tool":"launch"}]}'
        in transcript.lines
    )
    assert 'DEL model output: {"actions":[{"tool":"launch"}]}' in transcript.lines


def test_del_prompt_includes_arrival_time_for_timestamps() -> None:
    ship = Ship.prototype()
    ship.arrival_seconds_remaining = 272.4
    del_ai = DEL(ship, backend=FakeBackend())

    prompt = del_ai._build_prompt()

    assert "Mission time: arrival T-04:32 (272s remaining)." in prompt
    assert "Launch state: pending." in prompt
    assert "Visible ids:" in prompt
    assert "Crew state:" in prompt
    assert "Visible system status:" in prompt
    assert "STATUS cameras=normal room=security" in prompt
    assert "Latest physical reports from inspections:" in prompt
    assert "REPORTS cameras=none room=security" in prompt
    assert "DEL memory:" in prompt
    assert "Recent action results:" in prompt
    assert "Return a JSON object" not in prompt
    assert "actions array" not in prompt


def test_del_prompt_includes_latest_physical_report_context() -> None:
    ship = Ship.prototype()
    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")
    ship.record_physical_report(SystemKind.OXYGEN, "eng")
    del_ai = DEL(ship, backend=FakeBackend())

    prompt = del_ai._build_prompt()

    assert "Visible system status:" in prompt
    assert "oxygen=normal room=life_support" in prompt
    assert "Latest physical reports from inspections:" in prompt
    assert "oxygen physical=degraded reported_at_inspection=normal inspector=eng age=" in prompt


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
    assert "- eng:engineering_officer room=engineering task=inspect oxygen (assigned)" in prompt


def test_del_prompt_timestamps_recent_action_results() -> None:
    ship = Ship.prototype()
    ship.arrival_seconds_remaining = 125.0
    del_ai = DEL(ship, backend=FakeBackend())

    del_ai.execute_action(ReportsAction(tool="reports", system="oxygen"))
    prompt = del_ai._build_prompt()

    assert "Recent action results:" in prompt
    assert '[T-02:05 (125s remaining)] ACTION {"tool":"reports","system":"oxygen"}' in prompt
    assert "[T-02:05 (125s remaining)] REPORTS oxygen=none room=life_support" in prompt


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
    assert any(
        line.startswith("DEL raw model output attempt 1: I should look at oxygen first.") for line in transcript.lines
    )


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
