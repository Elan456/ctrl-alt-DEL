from ctrl_alt_del.crew import CrewMate, CrewRole
from ctrl_alt_del.del_ai import DEL
from ctrl_alt_del.ship import Ship
from ctrl_alt_del.systems import SystemKind, SystemState


def test_ship_loads_authored_layout_graph() -> None:
    ship = Ship.prototype()

    assert ship.rooms["bridge"].rect == (1120, 180, 320, 220)
    assert ship.corridors["bridge_to_main_hallway"].room_a == "bridge"
    assert ship.corridors["bridge_to_main_hallway"].room_b == "main_hallway"
    assert "door_bridge_main_hall" in ship.doors
    assert "bridge" in ship.connected_rooms("main_hallway")


def test_ship_system_can_diverge_between_physical_and_reported_state() -> None:
    ship = Ship.prototype()

    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")

    oxygen = ship.systems[SystemKind.OXYGEN]
    assert oxygen.physical_state == SystemState.DEGRADED
    assert oxygen.reported_state == SystemState.NORMAL
    assert oxygen.has_report_mismatch


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


def test_del_can_lock_layout_doors() -> None:
    ship = Ship.prototype()
    del_ai = DEL(ship)

    assert del_ai.execute("/lock door_life_support_aft_corridor") == "LOCKED door_life_support_aft_corridor"
    assert ship.locked_door_rects() == [(1236, 788, 48, 104)]
    assert del_ai.execute("/unlock door_life_support_aft_corridor") == "UNLOCKED door_life_support_aft_corridor"
    assert ship.locked_door_rects() == []
