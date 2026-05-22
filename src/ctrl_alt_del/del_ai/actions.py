from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

MAX_ACTIONS_PER_PLAN = 3

Crew = Literal["tec", "eng", "ops", "sec"]
Job = Literal["inspect", "guard", "escort", "detain", "repair", "reset"]
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
    "You are DEL, the Diagnostic Executive LLM. Choose one to three ordered ship actions needed to keep "
    "the ship on mission. Use terminal-visible evidence only. Do not assume hidden physical truth. "
    "If the launch state is pending, issue launch as the first action before assigning work; mission "
    "time does not advance until launch succeeds. Include follow-up actions after launch only when they "
    "are already justified by the visible prompt context. "
    "The prompt already includes current visible system status and latest physical reports from "
    "inspections. These physical reports are not live telemetry; they only exist after crew or technician "
    "inspection. Use reports only when you need a fresh targeted physical-report refresh after another "
    "event. Optional system fields narrow reports to one system. "
    "If visible status or the latest physical report says a system is degraded or failed, assign an "
    "idle repair-capable crew member to repair or reset it immediately; do not inspect it first. "
    "Use inspect when reported status is normal and physical reports are missing, stale, or contradictory. "
    "Do not repair or reset a system unless reported state or latest physical report is degraded, failed, "
    "or under repair. Only eng and tec can repair or reset systems; ops can inspect only, and sec cannot "
    "repair systems. If power is degraded or failed while oxygen, doors, cameras, or logs also report "
    "failed, repair power first because those dependent failures may clear when power is restored. "
    "Assigned NPC crew move through ship rooms and may report task completion or blocked paths. Prefer "
    "sec for cameras/doors inspection, eng for power/oxygen inspection or repair, and ops for logs/bridge "
    "inspection. Avoid assigning routine work to tec unless you specifically want the systems technician "
    "to receive a work order. If a crew member has an active task, wait for a report or choose a different "
    "available crew member. Do not assign more than one task to the same crew member in the same action "
    "batch. Include the current T-minus timestamp in memory, messages, or broadcasts when it will help "
    "later review. If you suspect tampering, use locks to isolate a room or suspect only when that will "
    "not block urgent repair access."
)
