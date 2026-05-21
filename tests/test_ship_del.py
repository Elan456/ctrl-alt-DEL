from ctrl_alt_del.crew import CrewMate, CrewRole
from ctrl_alt_del.del_ai import DEL
from ctrl_alt_del.ship import Ship
from ctrl_alt_del.systems import SystemKind, SystemState


def test_ship_system_can_diverge_between_physical_and_reported_state() -> None:
    ship = Ship.prototype()

    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")

    oxygen = ship.systems[SystemKind.OXYGEN]
    assert oxygen.physical_state == SystemState.DEGRADED
    assert oxygen.reported_state == SystemState.NORMAL
    assert oxygen.is_spoofed


def test_del_terminal_commands_use_reported_state_and_assign_tasks() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship)

    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")

    assert "oxygen=normal" in del_ai.execute("/status oxygen")
    assert del_ai.execute("/task eng repair oxygen") == "TASK eng repair oxygen"
    assert engineer.task is not None
    assert engineer.task.kind == "repair"
    assert engineer.task.target == "oxygen"
