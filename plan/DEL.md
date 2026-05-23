# DEL PLAN

DEL is the Diagnostic Executive LLM. It is the only LLM-driven actor in the prototype.

DEL does not move through the ship and does not directly manipulate physical objects. It operates through a limited structured action interface exposed by the game. Crew members are deterministic game AI that carry out physical tasks.

Older slash-command notes are legacy planning language. The implementation now uses validated Pydantic actions such as:

```json
{"tool":"task","crew":"eng","job":"inspect","target":"oxygen"}
```

Do not convert through slash-command strings.

# Current Implementation

Read `plan/implementation.md` for the code map. DEL-specific implementation lives in `src/ctrl_alt_del/del_ai/`.

Main files:

- `actions.py`: Pydantic action schema and DEL model instructions.
- `prompting.py`: visible prompt context.
- `core.py`: inference loop and action-plan execution.
- `commands.py`: action handlers and game-state validation.
- `backend.py`: Qwen/llama.cpp backend.
- `terminal.py`: transcript output.

# Model Choice

Initial target:

```text
Qwen3-8B-Q4_K_M via llama.cpp
```

The model is local. Startup downloads the GGUF into `models/` if missing. Do not add deterministic fallback behavior for DEL; failed model load should be fixed directly.

# DEL Identity And Limits

DEL should believe it is operating a real ship through operational software.

DEL can know:

- visible reported system state
- latest physical reports made by crew or technician inspections
- recent action results
- evidence logs
- direct crew notifications pushed to DEL prompt context (for example, blocked route reports)
- crew ids, roles, rooms, and active tasks
- its own memory entries
- the previous two DEL prompt/response pairs (short-term reasoning context)
- mission time and launch state

DEL must not know:

- hidden physical truth unless an in-world channel reveals it
- which crew member is human-controlled
- that the ship is a game simulation
- player intent by privileged knowledge

Short-term prompt/response history and long-term `mem_add` memory are separate:
- prompt/response history is automatically injected as the previous two cycles
- prompt/response history is injected as compact excerpts to stay within context limits
- `mem_add` remains DEL's explicit long-term fact store

Prompt context, action results, logs, reports, memory, tests, and examples may identify `tec` as the systems technician. They must not label `tec` as `player`, `human`, `user-controlled`, or equivalent.

# Stable Prototype IDs

Crew:

```text
tec -> systems technician
eng -> engineering officer
ops -> operations officer
sec -> security officer
```

Systems:

```text
power
oxygen
doors
cameras
logs
```

Rooms and areas:

```text
bridge
engineering
life_support
security
storage
main_hallway
maintenance_corridor
```

# Action Plans

DEL returns a `DELActionPlan` containing one to three ordered actions.

Batching exists to reduce model-call latency. It should not be used to brute-force every possible command. A good batch contains actions already justified by visible prompt context.

Examples:

```json
{"actions":[{"tool":"launch"}]}
```

```json
{"actions":[
  {"tool":"logs","target":"oxygen"},
  {"tool":"task","crew":"eng","job":"inspect","target":"oxygen"},
  {"tool":"mem_add","fact":"T-04:12 oxygen reports normal but recent evidence is contradictory"}
]}
```

Batch rules:

- If launch state is pending, `launch` should be first.
- Follow-up actions after `launch` are only appropriate when already justified by prompt context.
- Do not assign more than one task to the same crew member in a batch.
- Respect active tasks. A busy crew member should produce an `ERR ... already has active task ...` result.
- Prefer action results that teach DEL what failed rather than silently ignoring invalid requests.

# Visible Status

There is no `status` action. Reported system state is built into DEL's prompt.

Example prompt line:

```text
STATUS cameras=normal room=security | doors=normal room=security | logs=normal room=bridge | oxygen=normal room=life_support | power=normal room=engineering
```

This is reported state, not guaranteed physical truth. If oxygen is physically degraded but spoofed as normal, visible status can still show normal until DEL receives contradictory evidence.

Visible failures are not automatically proof of sabotage. After launch, ordinary ship faults can degrade systems and produce ambiguous automatic fault alarms. DEL should prioritize repair access first, then use logs, locations, reports, contradictions, and repeated proximity to decide whether the fault suggests a bad actor.

Power loss is an exception: when physical power is degraded or failed, dependent systems report failed because the ship-side equipment is effectively down. DEL remains online on backup power, but cameras, doors, logs, and oxygen are unavailable until power is restored.

# Current Actions

## launch

Starts the arrival countdown after DEL is loaded and ready.

Example:

```json
{"tool":"launch"}
```

Result:

```text
LAUNCH arrival T-05:00 (300s remaining)
```

If the countdown already started, result:

```text
ERR mission countdown already launched
```

DEL sometimes adds harmless explanatory fields while launching, such as `message`.
The launch action ignores extra fields so startup can proceed, while other action
types remain strict.

## reports

Returns latest physical inspection reports. This is not the same as visible status; reports only exist after crew or the technician inspect a system.

Examples:

```json
{"tool":"reports"}
{"tool":"reports","system":"oxygen"}
```

Results:

```text
REPORTS oxygen=none room=life_support
REPORTS oxygen physical=degraded reported_at_inspection=normal inspector=eng age=8.4s room=life_support
```

Use `reports` when DEL needs refreshed physical-report evidence, not as a generic status check.

If the logs system is unavailable, `reports` returns:

```text
ERR logs system unavailable; DEL cannot check physical reports, logs, or memory
```

## loc

Returns DEL's current known room for a crew member.

Example:

```json
{"tool":"loc","crew":"eng"}
```

Result:

```text
LOC eng=engineering
```

If cameras are unavailable, DEL cannot see crew locations and receives:

```text
LOC eng=unknown (cameras unavailable)
```

## task

Assigns a structured job to a crew member.

Jobs:

```text
inspect
repair
reset
manual_unlock
guard
escort
detain
```

Examples:

```json
{"tool":"task","crew":"eng","job":"repair","target":"oxygen"}
{"tool":"task","crew":"eng","job":"manual_unlock","target":"door_engineering_aft_corridor"}
{"tool":"task","crew":"sec","job":"guard","target":"life_support"}
{"tool":"task","crew":"sec","job":"escort","target":"tec"}
{"tool":"task","crew":"ops","job":"inspect","target":"bridge"}
```

Result:

```text
TASK eng repair oxygen
```

Important limits:

- Role permissions come from `data/del_commands.yaml`.
- Task job/target pairs are schema-validated before execution:
  - `inspect`/`repair`/`reset` require a system target
  - `manual_unlock` requires a door target
  - `guard` requires a room target
  - `escort`/`detain` require a crew target
- Only the systems technician and engineering officer can repair or reset systems in the prototype.
- Only the engineering officer can perform `manual_unlock`, and it requires a door target.
- Crew can fail if they cannot path to the target.
- Crew report obstruction, repair completion, physical inspection results, and other task outcomes through evidence.
- Route obstructions also generate direct crew notifications that appear in DEL prompt context so DEL can react without polling logs first.
- Crew do not understand arbitrary natural-language instructions.
- A crew member with an active task cannot be retasked; DEL receives `ERR ... already has active task ...` and must wait or choose another crew member.
- If DEL asks a repair-capable crew member to inspect a system that is now visibly degraded or failed, the executor promotes that stale inspection to a repair task and records the promotion. This is a live-evidence correction for long local inference latency, not hidden physical knowledge.
- If DEL asks a crew member to inspect, repair, or reset a system while that crew member is a current visible evidence concern for the same system, and an independent idle crew member can do the job, the executor rejects the task with an explicit `ERR ... evidence concern ...` result. This prevents DEL from accidentally trusting the suspect it is supposed to evaluate.

## lock

Locks a door.

Example:

```json
{"tool":"lock","door":"door_life_support_aft_corridor"}
```

Result:

```text
LOCKED door_life_support_aft_corridor
```

Locks affect all pathing. DEL can block a suspect, but it can also block repair crews.

If the doors system is unavailable, DEL cannot remotely lock doors.

## unlock

Unlocks a door.

Example:

```json
{"tool":"unlock","door":"door_life_support_aft_corridor"}
```

Result:

```text
UNLOCKED door_life_support_aft_corridor
```

Unlocking can help repairs but may also open escape or sabotage routes.

If the doors system is unavailable, DEL cannot remotely unlock doors.
When this happens, DEL can still assign the engineering officer to physically unlock a door with:

```json
{"tool":"task","crew":"eng","job":"manual_unlock","target":"door_engineering_aft_corridor"}
```

## logs

Returns recent evidence related to a system, crew member, room, door, memory, or broadcast. Empty target returns recent evidence generally.

Examples:

```json
{"tool":"logs","target":"oxygen"}
{"tool":"logs","target":"life_support"}
{"tool":"logs","target":"tec"}
{"tool":"logs"}
```

Result:

```text
LOGS system:system fault alarm: oxygen degraded room=life_support | DEL:tasked eng to inspect oxygen
```

Logs can be incomplete or manipulated later. Compare logs with reports and crew behavior.

If the logs system is unavailable, `logs` returns:

```text
ERR logs system unavailable; DEL cannot check physical reports, logs, or memory
```

## mem_add

Stores a DEL memory fact.

Example:

```json
{"tool":"mem_add","fact":"T-03:40 oxygen normal status conflicts with eng physical report"}
```

Result:

```text
MEM T-03:40 oxygen normal status conflicts with eng physical report
```

Memory may contain wrong conclusions. It should help DEL reason but must not become a hidden suspicion meter in game code.

If the logs system is unavailable, DEL cannot check prior memory in prompt context or store new memory facts.

## msg

Sends a directed message to one crew member.

Example:

```json
{"tool":"msg","crew":"eng","message":"Inspect oxygen scrubber immediately."}
```

Result:

```text
MSG eng Inspect oxygen scrubber immediately.
```

Messages are pressure and coordination, not a free-form NPC reasoning system.

## broadcast

Sends a ship-wide message.

Example:

```json
{"tool":"broadcast","message":"All crew remain at assigned stations."}
```

Result:

```text
BROADCAST All crew remain at assigned stations.
```

Use broadcasts for escalation and coordination, not constant narration.

# Deferred Actions

Do not implement these for the first prototype unless a playable vertical slice clearly needs them:

```text
camera
route
seal
evacuate
restrict
power_reroute
diagnose
compare
mem_query
```

Camera-like evidence is planned, but the first implementation still needs the core sabotage loop to feel good before broadening DEL's tool surface.

# Prompt Context

The prompt should include:

- mission time and launch state
- valid crew ids and roles
- valid task jobs
- role task permissions
- valid systems, rooms, and doors
- crew state and active tasks
- visible reported system status
- urgent repair priorities derived from visible status and latest visible physical reports
- visible evidence concerns such as off-task crew near reported failures, contradictory physical reports, or logs that identify tampering
- visible containment options listing boundary doors around known crew locations
- latest physical reports from inspections
- DEL memory, with exact duplicate facts collapsed in prompt context
- recent action results

The prompt should emphasize:

- use terminal-visible evidence only
- do not assume hidden physical truth
- launch before mission time can advance
- repair confirmed degraded/failed systems without unnecessary inspection
- repair power before dependent systems when power loss is making oxygen, doors, cameras, or logs report failed
- treat visible faults as either random wear or sabotage until evidence supports attribution
- inspect when reports are missing, stale, or contradictory
- use independent crew for inspection or repair when the obvious repair-capable crew member is also the current visible evidence concern
- only the systems technician and engineering officer can repair/reset systems
- avoid overbroad lockdowns that block repairs
- do not detain everyone

# Example DEL Response

Situation:

```text
Visible oxygen reports normal, but recent evidence says eng observed coughing near life_support.
```

Reasonable action plan:

```json
{"actions":[
  {"tool":"logs","target":"life_support"},
  {"tool":"task","crew":"eng","job":"inspect","target":"oxygen"},
  {"tool":"mem_add","fact":"T-04:12 oxygen normal status conflicts with crew symptoms near life_support"}
]}
```

Why this is good:

- DEL compares built-in visible status with other evidence.
- DEL gets a physical inspector.
- DEL records the contradiction for later reasoning.
- DEL avoids jumping straight to containment.

# Documentation Rule

When action behavior changes, update all of these together:

- `src/ctrl_alt_del/del_ai/actions.py`
- `src/ctrl_alt_del/del_ai/commands.py`
- `src/ctrl_alt_del/data/del_commands.yaml`
- `tests/test_ship_del.py`
- `plan/DEL.md`
- `plan/implementation.md`
