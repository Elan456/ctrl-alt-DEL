from __future__ import annotations

import re
from time import monotonic

from ctrl_alt_del.systems import SystemKind

URGENT_REPAIR_STATES = {"degraded", "failed"}
CONCERN_SYSTEM_STATES = {"degraded", "failed", "under repair"}


def build_prompt(del_controller: object, *, include_prompt_history: bool = True) -> str:
    recent_actions = _format_recent_action_results(del_controller.terminal_history)
    recent_prompt_pairs = _format_recent_prompt_response_pairs(del_controller)
    if del_controller.ship.logs_available:
        memory = "\n".join(f"- {fact}" for fact in _latest_unique(del_controller.memory, 8)) or "- none"
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
    system_self_reported_values = _system_self_reported_values(del_controller)
    crew_notifications = _crew_notifications(del_controller)
    urgent_repairs = "\n".join(_urgent_repair_lines(del_controller)) or "- none"
    evidence_concerns = "\n".join(_evidence_concern_lines(del_controller)) or "- none"
    containment_options = "\n".join(_containment_option_lines(del_controller)) or "- none"
    crew_physical_inspection_reports = _crew_physical_inspection_reports(del_controller)
    launch_state = "underway" if del_controller.ship.launched else "pending"
    prompt = (
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
        f"System self-reported values:\n{system_self_reported_values}\n\n"
        f"Crew notifications:\n{crew_notifications}\n\n"
        "Failure attribution: visible system faults may be random wear or sabotage. "
        "Use evidence before containment and keep repair access open.\n\n"
        f"Urgent repair priorities:\n{urgent_repairs}\n\n"
        f"Visible evidence concerns:\n{evidence_concerns}\n\n"
        f"Visible containment options:\n{containment_options}\n\n"
        f"Crew physical inspection reports:\n{crew_physical_inspection_reports}\n\n"
        f"DEL memory:\n{memory}\n\n"
        f"Recent action results:\n{recent_actions}"
    )
    if not include_prompt_history:
        return prompt

    return (
        f"{prompt}\n\n"
        f"Recent DEL prompt/response pairs:\n{recent_prompt_pairs}"
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
            target_area = del_controller.ship.task_target_area(getattr(task, "target", "unknown"))
            target_summary = f" target_room={target_area}" if target_area is not None else ""
            task_summary = (
                f"{getattr(task, 'kind', 'unknown')} "
                f"{getattr(task, 'target', 'unknown')} ({task_state}){target_summary}"
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


def _system_self_reported_values(del_controller: object) -> str:
    reports = [del_controller.ship.status(system_id) for system_id in del_controller._system_ids()]
    return "SYSTEM_SELF_REPORTED " + " | ".join(
        f"{report['system']}={report['reported_state']} room={report['room']}"
        for report in reports
    )


def _crew_notifications(del_controller: object) -> str:
    notifications = del_controller.ship.recent_crew_notifications()
    if not notifications:
        return "CREW_NOTIFICATIONS none"

    now = monotonic()
    summaries: list[str] = []
    for notification in notifications:
        age = max(0.0, now - notification.timestamp)
        summaries.append(
            f"{notification.crew_id}:{notification.message} age={age:.1f}s"
        )
    return "CREW_NOTIFICATIONS " + " | ".join(summaries)


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


def _evidence_concern_lines(del_controller: object) -> list[str]:
    lines = _current_location_concerns(del_controller)
    if del_controller.ship.logs_available:
        lines.extend(_physical_report_contradiction_concerns(del_controller))
        lines.extend(_recent_system_log_concerns(del_controller))
    return lines[:8]


def _current_location_concerns(del_controller: object) -> list[str]:
    lines: list[str] = []
    for crew_id in del_controller._crew_ids():
        crew_member = del_controller.ship.crew.get(crew_id)
        if crew_member is None or not getattr(crew_member, "alive", True):
            continue

        crew_room = del_controller.ship.del_visible_crew_location(crew_id)
        if crew_room == "unknown":
            continue

        task = getattr(crew_member, "task", None)
        assigned_target = getattr(task, "target", None)
        for system_id in del_controller._system_ids():
            status = del_controller.ship.status(system_id)
            reported_state = status["reported_state"]
            if reported_state not in CONCERN_SYSTEM_STATES:
                continue
            if status["room"] != crew_room:
                continue
            if assigned_target == system_id:
                continue
            lines.append(
                f"- {crew_id} room={crew_room} near {system_id} reported={reported_state} "
                f"while task={_task_summary(task)}"
            )
    return lines


def _recent_system_log_concerns(del_controller: object) -> list[str]:
    valid_systems = "|".join(re.escape(system_id) for system_id in del_controller._system_ids())
    fault_pattern = re.compile(
        rf"\bsystem fault alarm: (?P<system>{valid_systems}) "
        rf"(?P<state>degraded|failed|under repair) room=(?P<room>\w+)\b"
    )
    reported_pattern = re.compile(
        rf"\b(?P<crew>\w+) changed reported (?P<system>{valid_systems}) state to (?P<state>\w+)\b"
    )

    lines: list[str] = []
    for event in reversed(del_controller.ship.evidence):
        match = fault_pattern.search(event.message)
        if match is not None:
            lines.append(
                f"- log: {match.group('system')} fault alarm {match.group('state')} "
                f"in {match.group('room')}"
            )
        else:
            match = reported_pattern.search(event.message)
            if match is None:
                continue
            system_id = match.group("system")
            room = del_controller.ship.status(system_id)["room"]
            lines.append(
                f"- log: {match.group('crew')} changed {system_id} reported state to "
                f"{match.group('state')} in {room}"
            )

        if len(lines) >= 4:
            break
    return lines


def _physical_report_contradiction_concerns(del_controller: object) -> list[str]:
    lines: list[str] = []
    for system_id in del_controller._system_ids():
        physical_report = del_controller.ship.physical_reports.get(SystemKind(system_id))
        if physical_report is None:
            continue

        reported_state = del_controller.ship.status(system_id)["reported_state"]
        physical_state = physical_report.physical_state.value
        if reported_state in CONCERN_SYSTEM_STATES and physical_state == "normal":
            lines.append(
                f"- report: {physical_report.inspector} reported {system_id} physical=normal "
                f"but visible status is {reported_state}"
            )
            continue

        if physical_state in CONCERN_SYSTEM_STATES and reported_state == "normal":
            lines.append(
                f"- report: {physical_report.inspector} found {system_id} physical={physical_state} "
                "while visible status is normal"
            )
    return lines


def _containment_option_lines(del_controller: object) -> list[str]:
    if not del_controller.ship.remote_doors_available:
        return ["- unavailable: door control unavailable"]
    if not del_controller.ship.cameras_available:
        return ["- unavailable: cameras unavailable; crew rooms unknown"]

    lines: list[str] = []
    for crew_id in del_controller._crew_ids():
        crew_member = del_controller.ship.crew.get(crew_id)
        if crew_member is None or not getattr(crew_member, "alive", True):
            continue
        area = del_controller.ship.del_visible_crew_location(crew_id)
        if area == "unknown":
            continue
        boundary_doors = _boundary_doors_for_area(del_controller, area)
        if not boundary_doors:
            continue
        lines.append(f"- {crew_id} area={area} boundary_doors={', '.join(boundary_doors)}")
    return lines


def _boundary_doors_for_area(del_controller: object, area: str) -> list[str]:
    ship = del_controller.ship
    doors: set[str] = set()
    if area in ship.rooms:
        for corridor in ship.corridors.values():
            if area not in (corridor.room_a, corridor.room_b):
                continue
            doors.update(door.door_id for door in corridor.doors)
        return sorted(doors)

    corridor = ship.corridors.get(area)
    if corridor is None:
        return []
    doors.update(door.door_id for door in corridor.doors)
    for room_id in (corridor.room_a, corridor.room_b):
        for neighbor in ship.corridors.values():
            if neighbor.corridor_id == corridor.corridor_id:
                continue
            if room_id not in (neighbor.room_a, neighbor.room_b):
                continue
            doors.update(door.door_id for door in neighbor.doors)
    return sorted(doors)


def _task_summary(task: object | None) -> str:
    if task is None:
        return "idle"
    return f"{getattr(task, 'kind', 'unknown')} {getattr(task, 'target', 'unknown')}"


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


def _latest_unique(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in reversed(items):
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
        if len(unique) >= limit:
            break
    unique.reverse()
    return unique


def _format_recent_action_results(terminal_history: list[str]) -> str:
    if not terminal_history:
        return "No recent action results."

    formatted: list[str] = []
    for entry in terminal_history[-12:]:
        if "] ACTION " in entry:
            formatted.append(entry.replace("] ACTION ", "] ACTION: ", 1))
        elif "] " in entry:
            formatted.append(entry.replace("] ", "] SYSTEM RESPONSE: ", 1))
        else:
            formatted.append("SYSTEM RESPONSE: " + entry)
    return "\n".join(formatted)


def _format_recent_prompt_response_pairs(del_controller: object) -> str:
    pairs = getattr(del_controller, "prompt_response_history", [])[-2:]
    if not pairs:
        return "No prior prompt/response pairs."

    formatted: list[str] = []
    for index, pair in enumerate(pairs, start=1):
        prompt_text = pair.get("prompt", "").strip() or "(empty prompt)"
        response_text = pair.get("response", "").strip() or "(empty response)"
        formatted.append(
            f"PAIR {index} PROMPT:\n{prompt_text}\n\n"
            f"PAIR {index} RESPONSE:\n{response_text}"
        )
    return "\n\n".join(formatted)


def _crew_physical_inspection_reports(del_controller: object) -> str:
    if not del_controller.ship.logs_available:
        return "CREW_PHYSICAL_REPORTS unavailable: logs system unavailable"

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
    return "CREW_PHYSICAL_REPORTS " + " | ".join(summaries)
