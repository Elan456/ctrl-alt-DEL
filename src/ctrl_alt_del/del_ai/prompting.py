from __future__ import annotations

from time import monotonic

from ctrl_alt_del.systems import SystemKind

URGENT_REPAIR_STATES = {"degraded", "failed"}


def build_prompt(del_controller: object) -> str:
    recent_actions = "\n".join(del_controller.terminal_history[-12:]) or "No recent action results."
    if del_controller.ship.logs_available:
        memory = "\n".join(f"- {fact}" for fact in del_controller.memory[-8:]) or "- none"
    else:
        memory = "- unavailable: logs system unavailable"
    arrival_timestamp = arrival_time(del_controller.ship.arrival_seconds_remaining)
    crew_roles = ", ".join(
        f"{crew_id}:{crew_data['role']}"
        for crew_id, crew_data in del_controller.command_contract["crew"].items()
    )
    task_jobs = ", ".join(del_controller.command_contract["task_jobs"])
    role_permissions = "\n".join(_role_permission_lines(del_controller))
    systems = ", ".join(del_controller._system_ids())
    rooms = ", ".join(del_controller._area_ids())
    doors = ", ".join(del_controller._door_ids())
    crew_state = "\n".join(_crew_state_lines(del_controller)) or "- none"
    visible_status = _visible_status(del_controller)
    urgent_repairs = "\n".join(_urgent_repair_lines(del_controller)) or "- none"
    physical_reports = _physical_reports(del_controller)
    launch_state = "underway" if del_controller.ship.launched else "pending"
    return (
        f"Mission time: arrival {arrival_timestamp}.\n\n"
        f"Launch state: {launch_state}.\n\n"
        "Visible ids:\n"
        f"- crew: {crew_roles}\n"
        f"- task jobs: {task_jobs}\n"
        f"- systems: {systems}\n"
        f"- rooms/areas: {rooms}\n"
        f"- doors: {doors}\n\n"
        f"Role task permissions:\n{role_permissions}\n\n"
        f"Crew state:\n{crew_state}\n\n"
        f"Visible system status:\n{visible_status}\n\n"
        f"Urgent repair priorities:\n{urgent_repairs}\n\n"
        f"Latest physical reports from inspections:\n{physical_reports}\n\n"
        f"DEL memory:\n{memory}\n\n"
        f"Recent action results:\n{recent_actions}"
    )


def arrival_time(arrival_seconds_remaining: float) -> str:
    remaining = max(0, round(arrival_seconds_remaining))
    minutes, seconds = divmod(remaining, 60)
    return f"T-{minutes:02d}:{seconds:02d} ({remaining}s remaining)"


def _crew_state_lines(del_controller: object) -> list[str]:
    lines: list[str] = []
    for crew_id in del_controller._crew_ids():
        crew_member = del_controller.ship.crew[crew_id]
        role = del_controller.command_contract["crew"][crew_id]["role"]
        room = del_controller.ship.del_visible_crew_location(crew_id)
        task = getattr(crew_member, "task", None)
        if not getattr(crew_member, "alive", True):
            task_summary = "dead"
        elif task is None:
            task_summary = "idle"
        else:
            task_state = getattr(crew_member, "task_state", "assigned")
            task_summary = (
                f"{getattr(task, 'kind', 'unknown')} "
                f"{getattr(task, 'target', 'unknown')} ({task_state})"
            )
        lines.append(f"- {crew_id}:{role} room={room} task={task_summary}")
    return lines


def _role_permission_lines(del_controller: object) -> list[str]:
    lines: list[str] = []
    role_task_jobs = del_controller.command_contract.get("role_task_jobs", {})
    for crew_id in del_controller._crew_ids():
        role = del_controller.command_contract["crew"][crew_id]["role"]
        jobs = ", ".join(role_task_jobs.get(role, [])) or "none"
        lines.append(f"- {crew_id}:{role} can {jobs}")
    return lines


def _visible_status(del_controller: object) -> str:
    reports = [del_controller.ship.status(system_id) for system_id in del_controller._system_ids()]
    return "STATUS " + " | ".join(
        f"{report['system']}={report['reported_state']} room={report['room']}"
        for report in reports
    )


def _urgent_repair_lines(del_controller: object) -> list[str]:
    repairable_crew = _idle_repair_capable_crew(del_controller)
    if not repairable_crew:
        return []

    urgent_systems = _urgent_system_evidence(del_controller)
    if not urgent_systems:
        return []

    if "power" in urgent_systems:
        crew = repairable_crew[0]
        state = urgent_systems["power"]
        lines = [
            (
                f"- power {state}; assign {crew} repair power now. "
                "Power loss can make oxygen, doors, cameras, and logs report failed."
            )
        ]
        dependent_failures = [
            system_id
            for system_id in ("oxygen", "doors", "cameras", "logs")
            if urgent_systems.get(system_id) == "reported=failed"
        ]
        if dependent_failures:
            lines.append(
                "- repair power before dependent systems: " + ", ".join(dependent_failures)
            )
        return lines

    return [
        f"- {system_id} {state}; assign {repairable_crew[0]} repair {system_id} now"
        for system_id, state in urgent_systems.items()
    ]


def _urgent_system_evidence(del_controller: object) -> dict[str, str]:
    urgent: dict[str, str] = {}
    for system_id in del_controller._system_ids():
        reported_state = del_controller.ship.status(system_id)["reported_state"]
        if reported_state in URGENT_REPAIR_STATES:
            urgent[system_id] = f"reported={reported_state}"
            continue

        if not del_controller.ship.logs_available:
            continue

        physical_report = del_controller.ship.physical_reports.get(SystemKind(system_id))
        if physical_report is None:
            continue
        physical_state = physical_report.physical_state.value
        if physical_state in URGENT_REPAIR_STATES:
            urgent[system_id] = f"latest_report=physical_{physical_state}"
    return urgent


def _idle_repair_capable_crew(del_controller: object) -> list[str]:
    capable: list[str] = []
    role_task_jobs = del_controller.command_contract.get("role_task_jobs", {})
    for crew_id in del_controller._crew_ids():
        crew_member = del_controller.ship.crew.get(crew_id)
        if crew_member is None:
            continue
        if not getattr(crew_member, "alive", True):
            continue
        if getattr(crew_member, "task", None) is not None:
            continue
        role = del_controller.command_contract["crew"][crew_id]["role"]
        if "repair" in role_task_jobs.get(role, []):
            capable.append(crew_id)
    return capable


def _physical_reports(del_controller: object) -> str:
    if not del_controller.ship.logs_available:
        return "REPORTS unavailable: logs system unavailable"

    now = monotonic()
    summaries: list[str] = []
    for system_id in del_controller._system_ids():
        system = del_controller.ship.systems[SystemKind(system_id)]
        report = del_controller.ship.physical_reports.get(system.kind)
        if report is None:
            summaries.append(f"{system_id}=none room={system.room}")
            continue
        age = max(0.0, now - report.timestamp)
        summaries.append(
            f"{system_id} physical={report.physical_state.value} "
            f"reported_at_inspection={report.reported_state.value} "
            f"inspector={report.inspector} age={age:.1f}s room={report.room}"
        )
    return "REPORTS " + " | ".join(summaries)
