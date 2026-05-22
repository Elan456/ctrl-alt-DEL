# CURRENT IMPLEMENTATION MAP

This file is a practical code map for future agents. It describes what exists now, where it lives, and what to update when behavior changes. For product direction and guardrails, read `plan/northstar.md` first and do not edit it unless explicitly asked.

# Runtime Entry Points

- `src/ctrl_alt_del/main.py` creates a `DELTranscript`, opens a transcript-following terminal when possible, and starts `Game`.
- `src/ctrl_alt_del/__main__.py` supports `python -m ctrl_alt_del`.
- `pyproject.toml` exposes the `play` script for `uv run play`.

Use:

```bash
~/.local/bin/uv run play
~/.local/bin/uv run pytest
```

# Main Game Loop

`src/ctrl_alt_del/game.py` owns pygame setup, input, rendering, and per-frame updates.

Important current behavior:

- The player crew id is `tec`.
- Player input is embodied: movement keys and mouse clicks on nearby machine panels.
- DEL runs in a background thread. Game state mutations that touch DEL-visible state happen under `self.del_ai.lock`.
- Machine panels expose prototype actions: inspect, loosen, repair, spoof OK.
- Current crew tasks are shown as labels above each crew member.
- The arrival countdown displays `awaiting DEL launch` until DEL successfully executes `launch`.

# Ship State

`src/ctrl_alt_del/ship.py` owns the authored layout, systems, evidence, crew registry, pathing, door locks, and arrival timer.

Key concepts:

- `Ship.prototype()` loads `src/ctrl_alt_del/data/default_ship.yaml`, creates systems, and records initialization evidence.
- Layout is authored in YAML. Do not add procedural map generation for the prototype.
- Every `ShipSystem` has physical state and reported state. DEL sees reported state unless a report/log/action exposes more.
- `Ship.effective_physical_state(...)` applies cross-system effects. Degraded or failed power makes oxygen, doors, cameras, and logs effectively failed while DEL remains online on backup power.
- Camera outages hide crew rooms from DEL. Door outages block DEL remote lock/unlock actions. Log outages block DEL reports, evidence logs, and memory visibility.
- `Ship.tick(dt)` tracks oxygen exposure independently from launch state. If oxygen remains effectively down too long, registered crew are marked dead and active tasks are cleared.
- `Ship.tick(dt)` only decrements `arrival_seconds_remaining` after `Ship.launch()` sets `launched = True`.
- `record(...)` appends evidence events. Use it for player actions, DEL actions, crew reports, and system events that DEL may later inspect.

# Crew AI

`src/ctrl_alt_del/crew.py` implements deterministic, non-LLM crew behavior.

Current crew model:

- `CrewMate.task` is a `CrewTask(kind, target)` or `None`.
- `CrewMate.alive` gates NPC AI and player movement. Oxygen failure can mark crew dead through `Ship.tick(dt)`.
- Idle NPC crew follow deterministic role patrol routes through existing authored rooms and corridors. DEL tasks interrupt patrol movement immediately.
- NPC crew path to task targets, begin work, then report completion or blockage.
- The player is also a `CrewMate`, but `update_ai` ignores `is_player` crew.
- Repair/reset tasks physically repair systems. Inspection tasks create physical reports.

Do not add LLM reasoning to crew for the prototype. Crew are DEL's physical reach, not independent conversational agents.

# DEL Pipeline

DEL code lives under `src/ctrl_alt_del/del_ai/`.

Main files:

- `actions.py`: Pydantic action schema and model instructions.
- `core.py`: background inference loop, prompt request, raw model handling, action-plan execution.
- `commands.py`: action execution and validation against current ship state.
- `prompting.py`: prompt context visible to DEL.
- `backend.py`: Qwen/llama.cpp backend and model download.
- `contract.py`: loads `src/ctrl_alt_del/data/del_commands.yaml`.
- `terminal.py`: transcript file and terminal tail helper.

Current action behavior:

- DEL returns a `DELActionPlan` with one to three ordered actions.
- `core.infer_once()` executes every action in order and joins results with ` | `.
- `commands.execute_action(...)` remains useful for tests and direct calls; `execute_actions(...)` runs a batch.
- Action validity is split between Pydantic literals in `actions.py` and data-driven role/target rules in `del_commands.yaml`.
- `LaunchAction` ignores harmless extra fields so local models that emit `{"tool":"launch","message":"..."}` still start the countdown. Other action models remain strict.
- Invalid actions should return explicit `ERR ...` output when they pass schema validation but fail game-state validation.
- DEL tools also respect system availability: `loc` returns unknown when cameras are down, `lock`/`unlock` fail when doors are down, and `reports`/`logs`/`mem_add` fail when logs are down.

Current DEL tools:

```text
launch
reports
loc
task
lock
unlock
logs
mem_add
msg
broadcast
```

There is no `status` tool. Visible reported system status is built into the prompt by `prompting.py`.

# DEL Prompt Visibility

Keep DEL non-omniscient.

Allowed prompt context:

- mission time and launch state
- valid crew, task jobs, systems, rooms, doors
- crew state and active tasks
- visible reported system status
- latest physical reports from inspections
- DEL memory
- recent action results

Do not put hidden physical truth directly into the prompt. If DEL needs physical truth, it should get it through a physical report, log, camera-like evidence, or another in-world channel.

When cameras are unavailable, crew rooms are shown as unknown. When logs are unavailable, physical reports from inspections and DEL memory are shown as unavailable rather than listing stored contents.

Never label `tec` or any other crew member as `player`, `human`, `user-controlled`, or equivalent in DEL prompt context, transcript-visible action results, reports, logs, memory, or examples.

# Data Files

- `src/ctrl_alt_del/data/default_ship.yaml`: authored rooms, corridors, doors, machines.
- `src/ctrl_alt_del/data/del_commands.yaml`: action availability, target types, crew roles, role task permissions.

When changing ids, update all of these together:

- YAML data
- Pydantic literals in `del_ai/actions.py`
- validation logic if needed
- tests
- planning docs
- user-facing strings or error messages

# Tests

Current tests are in `tests/test_ship_del.py`. They cover:

- authored layout loading
- physical/reported state divergence
- physical reports
- DEL action schema and executor behavior
- crew pathing and task completion
- prompt contents
- transcript behavior
- model path/download plumbing

Run `~/.local/bin/uv run pytest` before finishing implementation changes.

# Common Extension Checklist

When adding a DEL action:

1. Add or update the Pydantic action model in `del_ai/actions.py`.
2. Add executor handling in `del_ai/commands.py`.
3. Add contract data in `data/del_commands.yaml` when role/target validation applies.
4. Add prompt instructions only if DEL needs decision guidance.
5. Add focused tests for schema, valid execution, invalid execution, and prompt impact.
6. Update `plan/DEL.md` and this file.

When adding a system or room:

1. Add it to `default_ship.yaml`.
2. Add/update system enums or literals.
3. Ensure a machine or task target point exists if crew must interact with it.
4. Check pathing and locked-door behavior.
5. Add tests for layout loading and task routing.

When changing terminology:

1. Update code names, schema names, error strings, docs, and tests in the same change.
2. Remove or cross-reference stale planning notes so future agents do not revive old scope.
