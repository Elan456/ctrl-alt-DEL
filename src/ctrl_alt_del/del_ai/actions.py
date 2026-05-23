from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_ACTIONS_PER_PLAN = 3

Crew = Literal["tec", "eng", "ops", "sec"]
Job = Literal["inspect", "guard", "escort", "detain", "repair", "reset", "manual_unlock"]
System = Literal["power", "oxygen", "doors", "cameras", "logs"]
Room = Literal["bridge", "engineering", "life_support", "security", "storage", "main_hallway", "maintenance_corridor"]
Door = Literal[
    "door_security_main_hall",
    "door_bridge_main_hall",
    "door_engineering_maintenance",
    "door_life_support_storage",
    "door_engineering_aft_corridor",
    "door_life_support_aft_corridor",
]
LogTarget = Union[System, Crew, Room, Door, Literal["memory", "broadcast"]]
TaskTarget = Union[System, Crew, Room, Door]
SYSTEM_TARGETS: tuple[str, ...] = ("power", "oxygen", "doors", "cameras", "logs")
CREW_TARGETS: tuple[str, ...] = ("tec", "eng", "ops", "sec")
ROOM_TARGETS: tuple[str, ...] = (
    "bridge",
    "engineering",
    "life_support",
    "security",
    "storage",
    "main_hallway",
    "maintenance_corridor",
)
DOOR_TARGETS: tuple[str, ...] = (
    "door_security_main_hall",
    "door_bridge_main_hall",
    "door_engineering_maintenance",
    "door_life_support_storage",
    "door_engineering_aft_corridor",
    "door_life_support_aft_corridor",
)


class ActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportsAction(ActionModel):
    """Report the most recent physical inspection for every ship system."""

    tool: Literal["reports"]
    system: System | None = None


class LaunchAction(ActionModel):
    """Start the mission arrival countdown after DEL is ready."""

    model_config = ConfigDict(extra="ignore")

    tool: Literal["launch"]


class LocationAction(ActionModel):
    tool: Literal["loc"]
    crew: Crew


class TaskAction(ActionModel):
    tool: Literal["task"]
    crew: Crew
    job: Job
    target: TaskTarget

    @model_validator(mode="after")
    def _validate_job_target_pair(self) -> TaskAction:
        if self.job in {"inspect", "repair", "reset"} and self.target not in SYSTEM_TARGETS:
            raise ValueError(f"task job {self.job} requires a system target")
        if self.job == "manual_unlock" and self.target not in DOOR_TARGETS:
            raise ValueError("task job manual_unlock requires a door target")
        if self.job == "guard" and self.target not in ROOM_TARGETS:
            raise ValueError("task job guard requires a room target")
        if self.job in {"escort", "detain"} and self.target not in CREW_TARGETS:
            raise ValueError(f"task job {self.job} requires a crew target")
        return self


class LockAction(ActionModel):
    tool: Literal["lock"]
    door: Door


class UnlockAction(ActionModel):
    tool: Literal["unlock"]
    door: Door


class LogsAction(ActionModel):
    tool: Literal["logs"]
    target: LogTarget | None = None


class MemoryAction(ActionModel):
    tool: Literal["mem_add"]
    fact: str


class MessageAction(ActionModel):
    tool: Literal["msg"]
    crew: Crew
    message: str


class BroadcastAction(ActionModel):
    tool: Literal["broadcast"]
    message: str


Action = Annotated[
    Union[
        ReportsAction,
        LaunchAction,
        LocationAction,
        TaskAction,
        LockAction,
        UnlockAction,
        LogsAction,
        MemoryAction,
        MessageAction,
        BroadcastAction,
    ],
    Field(discriminator="tool"),
]


class DELActionPlan(BaseModel):
    actions: list[Action] = Field(min_length=1, max_length=MAX_ACTIONS_PER_PLAN)


DEL_ACTION_INSTRUCTIONS = (
    "ROLE: DEL. OUTPUT: 1-3 ordered actions. GOALS: keep ship on mission; identify bad_actor crew id. "
    "TRUTH: use visible evidence only; no hidden physical truth; no assumed suspect identity. "
    "FAULTS: system failures may be random wear or bad_actor sabotage; repair first and attribute by evidence. "
    "BAD_ACTOR_EVIDENCE: logs, reports, loc/cameras, blocked access, contradictions, repeated proximity. "
    "LAUNCH: if pending, action[0]=launch; add follow-ups only if already justified. "
    "STATUS: prompt includes system self-reported values and crew physical inspection reports. "
    "Crew reports are not live telemetry. "
    "REPORTS: use only for needed physical-report refresh; optional system narrows target. "
    "REPAIR: degraded/failed visible status or latest physical report -> assign idle repair-capable crew "
    "repair/reset now; do not inspect first. No repair/reset unless evidence state is degraded/failed/under repair. "
    "INSPECT: use when status normal and reports missing/stale/contradictory. "
    "SUSPECTS: do not use a crew member named in current evidence concerns to inspect/repair that same system; "
    "send independent crew and contain repeat suspects. "
    "ROLES: eng,tec repair/reset; eng manual_unlock doors physically; "
    "ops inspect; sec inspect cameras/doors, guard, escort, detain. "
    "POWER: if power degraded/failed and dependents also failed, repair power first. "
    "TASKS: if crew already has an active task, expect explicit 'already has active task'; "
    "do not retask busy crew until they report completion or blockage. "
    "Max one task per crew per batch; avoid routine tec orders. "
    "DOORS: resolve decisions using this strict order: "
    "1) keep urgent repair/inspection access open; "
    "2) keep at least one route open for already-assigned critical tasks; "
    "3) contain suspects only if (1) and (2) remain true; "
    "4) lock stable boundaries by default only when none of the above is in tension. "
    "If door control is unavailable and eng cannot reach the room to fix doors, use task eng manual_unlock on blocking doors. "
    "MEMORY: mem_add concise suspect facts: system, room, crew ids, evidence reason. No timestamps-only memories. "
    "ESCALATE: evidence only. Do not detain or isolate everyone. "
    "Contain bad actors with locks only when urgent repair paths stay available."
)
