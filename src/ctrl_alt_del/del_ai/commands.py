from __future__ import annotations

from collections.abc import Sequence
import re
from time import monotonic

from ctrl_alt_del.del_ai.actions import (
    Action,
    BroadcastAction,
    LaunchAction,
    LocationAction,
    LockAction,
    LogsAction,
    MemoryAction,
    MessageAction,
    ReportsAction,
    TaskAction,
    UnlockAction,
)
from ctrl_alt_del.systems import SystemKind

URGENT_REPAIR_STATES = {"degraded", "failed"}


class ActionExecutorMixin:
    def execute_action(self, action: Action) -> str:
        with self.lock:
            result = self._execute_action_locked(action)
        return result

    def execute_actions(self, actions: Sequence[Action]) -> str:
        with self.lock:
            results = [self._execute_action_locked(action) for action in actions]
        return " | ".join(results)

    def _execute_action_locked(self, action: Action) -> str:
        action_json = action.model_dump_json(exclude_none=True)
        self._write_transcript("ACTION " + action_json)

        try:
            if isinstance(action, ReportsAction):
                result = self._reports(action)
            elif isinstance(action, LaunchAction):
                result = self._launch(action)
            elif isinstance(action, LocationAction):
                result = self._loc(action)
            elif isinstance(action, TaskAction):
                result = self._task(action)
            elif isinstance(action, LockAction):
                result = self._lock(action)
            elif isinstance(action, UnlockAction):
                result = self._unlock(action)
            elif isinstance(action, LogsAction):
                result = self._logs(action)
            elif isinstance(action, MemoryAction):
                result = self._mem_add(action)
            elif isinstance(action, MessageAction):
                result = self._message(action)
            elif isinstance(action, BroadcastAction):
                result = self._broadcast(action)
            else:
                result = f"ERR unsupported action {action!r}"
        except (KeyError, ValueError, IndexError) as exc:
            result = f"ERR {exc}"

        self._append_terminal_history("ACTION " + action_json)
        self._append_terminal_history(result)
        self._write_transcript(result)
        return result

    def _reports(self, action: ReportsAction) -> str:
        if not self.ship.logs_available:
            return self._logs_unavailable()

        now = monotonic()
        summaries: list[str] = []
        system_ids = [action.system] if action.system is not None else self._system_ids()
        for system_id in system_ids:
            system = self.ship.systems[SystemKind(system_id)]
            report = self.ship.physical_reports.get(system.kind)
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

    def _launch(self, action: LaunchAction) -> str:
        if not self.ship.launch("DEL"):
            return "ERR mission countdown already launched"
        return f"LAUNCH arrival {self._arrival_time()}"

    def _loc(self, action: LocationAction) -> str:
        crew_id = action.crew
        if not self._is_crew(crew_id):
            return self._invalid_target("loc", crew_id, ["crew"])
        if not self.ship.cameras_available:
            return f"LOC {crew_id}=unknown (cameras unavailable)"
        return f"LOC {crew_id}={self.ship.del_visible_crew_location(crew_id)}"

    def _task(self, action: TaskAction) -> str:
        original_job = action.job
        original_target = action.target
        action, promotion_reason = self._promote_stale_system_inspection(action)
        crew_id, job, target = action.crew, action.job, action.target
        if not self._is_crew(crew_id):
            return self._invalid_target("task", crew_id, ["crew"])
        crew_member = self.ship.crew[crew_id]
        active_task = getattr(crew_member, "task", None)
        if active_task is not None:
            active_kind = getattr(active_task, "kind", "unknown")
            active_target = getattr(active_task, "target", "unknown")
            if active_kind == job and active_target == target:
                return f"TASK {crew_id} already has task {active_kind} {active_target}"
            return (
                f"ERR {crew_id} already has active task {active_kind} {active_target}; "
                f"cannot assign {job} {target}"
            )

        validation_error = self._validate_task(action)
        if validation_error is not None:
            return validation_error

        crew_member.assign_task(job, target)
        self.ship.record("DEL", f"tasked {crew_id} to {job} {target}", crew_id)
        result = f"TASK {crew_id} {job} {target}"
        if promotion_reason is not None:
            self.ship.record(
                "DEL",
                f"promoted stale task {crew_id} {original_job} {original_target} to {job} {target}: {promotion_reason}",
                target,
            )
            result += f" (promoted from {original_job}: {promotion_reason})"
        return result

    def _lock(self, action: LockAction) -> str:
        door_id = action.door
        if not self._is_door(door_id):
            return self._invalid_target("lock", door_id, ["door"])
        if not self.ship.remote_doors_available:
            return self._doors_unavailable("lock")
        self.ship.lock_door(door_id)
        return f"LOCKED {door_id}"

    def _unlock(self, action: UnlockAction) -> str:
        door_id = action.door
        if not self._is_door(door_id):
            return self._invalid_target("unlock", door_id, ["door"])
        if not self.ship.remote_doors_available:
            return self._doors_unavailable("unlock")
        self.ship.unlock_door(door_id)
        return f"UNLOCKED {door_id}"

    def _logs(self, action: LogsAction) -> str:
        if not self.ship.logs_available:
            return self._logs_unavailable()

        target = action.target
        if target is not None and self._target_type(target) not in self._command_target_types("logs"):
            return self._invalid_target("logs", target, self._command_target_types("logs"))
        events = self.ship.logs_for(target)[-5:]
        if not events:
            return "LOGS none"
        return "LOGS " + " | ".join(f"{event.source}:{event.message}" for event in events)

    def _mem_add(self, action: MemoryAction) -> str:
        if not self.ship.logs_available:
            return self._logs_unavailable()

        fact = action.fact.strip()
        if not fact:
            return "ERR mem_add requires a fact"
        if fact not in self.memory:
            self.memory.append(fact)
            self.ship.record("DEL", f"remembered: {fact}", "memory")
        return f"MEM {fact}"

    def _message(self, action: MessageAction) -> str:
        crew_id = action.crew
        if not self._is_crew(crew_id):
            return self._invalid_target("msg", crew_id, ["crew"])
        message = action.message.strip()
        if not message:
            return "ERR msg requires a message"
        self.ship.record("DEL", f"msg to {crew_id}: {message}", crew_id)
        return f"MSG {crew_id} {message}"

    def _broadcast(self, action: BroadcastAction) -> str:
        message = action.message.strip()
        if not message:
            return "ERR broadcast requires a message"
        self.ship.record("DEL", f"broadcast: {message}", "broadcast")
        return f"BROADCAST {message}"

    def _validate_task(self, action: TaskAction) -> str | None:
        crew_id, job, target = action.crew, action.job, action.target
        if not self._is_crew(crew_id):
            return self._invalid_target("task", crew_id, ["crew"])

        task_jobs = self.command_contract.get("task_jobs", {})
        if job not in task_jobs:
            return f"ERR invalid task job {job}; valid jobs: {', '.join(task_jobs)}"

        role = self.command_contract["crew"][crew_id]["role"]
        role_jobs = self.command_contract.get("role_task_jobs", {}).get(role, [])
        if job not in role_jobs:
            return f"ERR {crew_id} role {role} cannot perform task job {job}; valid jobs: {', '.join(role_jobs)}"

        allowed_target_types = task_jobs[job].get("target_types", [])
        target_type = self._target_type(target)
        if target_type not in allowed_target_types:
            return self._invalid_target(f"task {job}", target, allowed_target_types)

        suspect_assignment_error = self._validate_independent_system_task(
            crew_id, job, target, target_type
        )
        if suspect_assignment_error is not None:
            return suspect_assignment_error

        allowed_evidence_states = task_jobs[job].get("allowed_evidence_states")
        if allowed_evidence_states:
            if target_type != "system":
                return f"ERR task job {job} requires a system target"
            reported_state = self.ship.status(target)["reported_state"]
            physical_report = self.ship.physical_reports.get(SystemKind(target))
            physical_report_state = (
                physical_report.physical_state.value if physical_report is not None else None
            )
            if (
                reported_state not in allowed_evidence_states
                and physical_report_state not in allowed_evidence_states
            ):
                physical_summary = physical_report_state or "none"
                return (
                    f"ERR cannot {job} {target}: reported state is {reported_state}, "
                    f"latest physical report is {physical_summary}; "
                    f"allowed evidence states: {', '.join(allowed_evidence_states)}"
                )

        return None

    def _validate_independent_system_task(
        self,
        crew_id: str,
        job: str,
        target: str,
        target_type: str | None,
    ) -> str | None:
        if target_type != "system" or job not in {"inspect", "repair", "reset"}:
            return None
        if not self._crew_is_current_system_concern(crew_id, target):
            return None
        alternates = self._idle_crew_for_job(job, excluded_crew_id=crew_id)
        if not alternates:
            return None
        return (
            f"ERR {crew_id} is a current evidence concern for {target}; "
            f"use independent crew {', '.join(alternates)} or security containment"
        )

    def _crew_is_current_system_concern(self, crew_id: str, system_id: str) -> bool:
        if not self.ship.cameras_available:
            return False
        crew_member = self.ship.crew.get(crew_id)
        if crew_member is None or not getattr(crew_member, "alive", True):
            return False
        crew_room = self.ship.del_visible_crew_location(crew_id)
        if crew_room == "unknown":
            return False

        status = self.ship.status(system_id)
        if status["reported_state"] not in {"degraded", "failed", "under repair"}:
            return False
        if status["room"] != crew_room:
            return False

        task = getattr(crew_member, "task", None)
        assigned_target = getattr(task, "target", None)
        return assigned_target != system_id

    def _idle_crew_for_job(self, job: str, excluded_crew_id: str) -> list[str]:
        alternates: list[str] = []
        role_task_jobs = self.command_contract.get("role_task_jobs", {})
        for crew_id in self._crew_ids():
            if crew_id == excluded_crew_id:
                continue
            crew_member = self.ship.crew.get(crew_id)
            if crew_member is None or not getattr(crew_member, "alive", True):
                continue
            if getattr(crew_member, "task", None) is not None:
                continue
            role = self.command_contract["crew"][crew_id]["role"]
            if job in role_task_jobs.get(role, []):
                alternates.append(crew_id)
        return alternates

    def _promote_stale_system_inspection(self, action: TaskAction) -> tuple[TaskAction, str | None]:
        if action.job != "inspect" or not self._is_system(action.target):
            return action, None

        crew_id = action.crew
        if not self._is_crew(crew_id):
            return action, None

        role = self.command_contract["crew"][crew_id]["role"]
        role_jobs = self.command_contract.get("role_task_jobs", {}).get(role, [])
        if "repair" not in role_jobs:
            return action, None

        crew_member = self.ship.crew[crew_id]
        if getattr(crew_member, "task", None) is not None:
            return action, None

        evidence_state = self._urgent_system_evidence_state(action.target)
        if evidence_state is None:
            return action, None

        promoted = action.model_copy(update={"job": "repair"})
        return promoted, evidence_state

    def _urgent_system_evidence_state(self, system_id: str) -> str | None:
        reported_state = self.ship.status(system_id)["reported_state"]
        if reported_state in URGENT_REPAIR_STATES:
            return f"current reported state is {reported_state}"

        if not self.ship.logs_available:
            return None

        physical_report = self.ship.physical_reports.get(SystemKind(system_id))
        if physical_report is None:
            return None

        physical_state = physical_report.physical_state.value
        if physical_state in URGENT_REPAIR_STATES:
            return f"latest physical report is {physical_state}"
        return None

    def _command_target_types(self, command: str) -> list[str]:
        command_data = self.command_contract.get("commands", {}).get(command, {})
        target_types = command_data.get("target_types", [])
        return list(target_types)

    def _target_type(self, target: str) -> str | None:
        if self._is_system(target):
            return "system"
        if self._is_crew(target):
            return "crew"
        if self._is_room_or_area(target):
            return "room"
        if self._is_door(target):
            return "door"
        if target in {"memory", "broadcast"}:
            return target
        return None

    def _invalid_target(self, action: str, target: str, allowed_types: list[str]) -> str:
        valid_examples: list[str] = []
        if "system" in allowed_types:
            valid_examples.extend(self._system_ids())
        if "crew" in allowed_types:
            valid_examples.extend(self._crew_ids())
        if "room" in allowed_types:
            valid_examples.extend(self._area_ids())
        if "door" in allowed_types:
            valid_examples.extend(self._door_ids())
        if "memory" in allowed_types:
            valid_examples.append("memory")
        if "broadcast" in allowed_types:
            valid_examples.append("broadcast")
        examples = ", ".join(valid_examples)
        return f"ERR invalid {action} target {target}; expected {'/'.join(allowed_types)}. Valid targets: {examples}"

    def _system_ids(self) -> list[str]:
        return sorted(system.value for system in self.ship.systems)

    def _crew_ids(self) -> list[str]:
        contract_crew = set(self.command_contract.get("crew", {}))
        return sorted(crew_id for crew_id in self.ship.crew if crew_id in contract_crew)

    def _area_ids(self) -> list[str]:
        return sorted([*self.ship.rooms, *self.ship.corridors])

    def _door_ids(self) -> list[str]:
        return sorted(self.ship.doors)

    def _is_system(self, target: str) -> bool:
        return target in self._system_ids()

    def _is_crew(self, target: str) -> bool:
        return target in self._crew_ids()

    def _is_room_or_area(self, target: str) -> bool:
        return target in self.ship.rooms or target in self.ship.corridors

    def _is_door(self, target: str) -> bool:
        return target in self.ship.doors

    @staticmethod
    def _logs_unavailable() -> str:
        return "ERR logs system unavailable; DEL cannot check physical reports, logs, or memory"

    @staticmethod
    def _doors_unavailable(action: str) -> str:
        return f"ERR door control unavailable; DEL cannot remotely {action} doors"

    @staticmethod
    def _remove_thinking(response: str) -> str:
        without_closed_blocks = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
        return re.sub(r"<think>.*", "", without_closed_blocks, flags=re.DOTALL)
