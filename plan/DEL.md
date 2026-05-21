# DEL PLAN

DEL is the Diagnostic Executive LLM.

It is the only LLM-driven actor in the prototype. DEL does not move through the ship and does not directly manipulate physical objects. It operates through a limited terminal command interface exposed by the game.

# Model Choice

Initial target:

```text
Qwen3-8B-Instruct Q4_K_M via llama.cpp
```

Reasoning:

- should fit on common 8 GB VRAM cards
- small enough for local play
- strong enough to reason over structured tool results
- known to work reasonably well with tool-like command formats

# Command Design Goals

DEL commands should be:

- structured enough for game code to parse
- readable enough for the player to understand if surfaced in logs
- limited enough that DEL is not omniscient
- tied to the prototype systems in `plan/systems.md`
- usable with the four-person roster in `plan/roles.md`

DEL sees reported state, logs, camera output, and crew reports. DEL does not get hidden physical truth unless a command result exposes it through an in-world source.

DEL should believe that it's operating a real ship. Nothing in the commands should use words like "player", "game" or "win". 

# Player Identity

DEL must not have an easy way to know which of the crew members is the actual player.
As soon as DEL knows who the human player is, it becomes trivial to identify the sabotour
By giving DEL and the player a limited interface to interact with each other, the player should 
be indistinguhable from a normal crew member except for the player not always doing tasks properly 
or being in weird rooms sometimes. 

# Prototype Crew IDs

Use stable ids:

```text
tec     -> Systems Technician
eng     -> Engineering Officer
ops     -> Operations Officer
sec     -> Security Officer
```

# Prototype Systems

Use stable system ids:

```text
power
oxygen
doors
cameras
logs
```

# Prototype Rooms

Use stable room ids:

```text
bridge
engineering
life_support
security
storage
main_hallway
maintenance_corridor
```

# Command List

## /status

Syntax:

```text
/status <system>
```

Purpose:

Returns the reported state of a system.

Examples:

```text
/status oxygen
/status power
/status cameras
```

Example result:

```text
STATUS oxygen=normal room=life_support
```

Important limit:

This command reports what the ship says, not necessarily physical truth. If oxygen is physically degraded but spoofed as normal, `/status oxygen` should return normal.

## /loc

Syntax:

```text
/loc <crew>
```

Purpose:

Returns DEL's current known room for a crew member.

Examples:

```text
/loc player
/loc eng
/loc sec
```

Example result:

```text
LOC player=maintenance_corridor
```

Important limit:

This should rely on available location evidence: access logs, camera sightings, crew reports, or tracker state. If those systems are degraded or spoofed later, location can become stale or uncertain.

## /task

Syntax:

```text
/task <crew> <job> <target>
```

Purpose:

Assigns a structured job to a non-LLM crew member.

Prototype jobs:

```text
inspect
repair
guard
escort
detain
fetch
report
```

Examples:

```text
/task eng repair oxygen
/task sec guard life_support
/task sec escort player
/task ops report mission_timer
/task eng inspect power
```

Example result:

```text
TASK eng repair oxygen
```

Important limits:

- Crew may fail if they cannot path to the target.
- Crew may report obstruction, danger, missing parts, or contradictory evidence.
- Crew do not understand arbitrary natural language in this command.
- The player may see or infer tasks through messages, crew movement, or logs.

## /lock

Syntax:

```text
/lock <door>
```

Purpose:

Locks a door or access route.

Examples:

```text
/lock door_engineering
/lock door_life_support
```

Example result:

```text
LOCKED door_life_support
```

Important limit:

Locks affect everyone who needs that route. DEL can trap the player, but it can also block repair crews.

## /unlock

Syntax:

```text
/unlock <door>
```

Purpose:

Unlocks a door or access route.

Examples:

```text
/unlock door_engineering
/unlock door_security
```

Example result:

```text
UNLOCKED door_engineering
```

Important limit:

Unlocking a route may help crew reach a repair, but it may also give the player an escape route.

## /logs

Syntax:

```text
/logs <target>
```

Purpose:

Returns recent log entries related to a crew member, room, system, door, or event category.

Examples:

```text
/logs player
/logs oxygen
/logs life_support
/logs door_life_support
/logs repairs
```

Example result:

```text
LOGS access:player entered life_support | repair:player reported oxygen repair complete
```

Important limits:

- Logs can be incomplete.
- Logs can be wiped or forged by the player.
- Logs should be compared with cameras and crew reports.

## /camera

Syntax:

```text
/camera <camera_or_room>
```

Purpose:

Returns a recent camera observation.

Examples:

```text
/camera main_hallway
/camera life_support
```

Example result:

```text
CAMERA life_support last_seen=player age=12s status=online
```

Important limits:

- Cameras can be disabled.
- Cameras can be looped.
- A camera result can be stale or misleading.
- Camera blind spots should matter.

## /msg

Syntax:

```text
/msg <crew> <message>
```

Purpose:

Sends a directed message to one crew member.

Examples:

```text
/msg eng "Inspect oxygen scrubber immediately."
/msg sec "Guard life support until further notice."
/msg player "Report to engineering for diagnostics."
```

Example result:

```text
MSG eng delivered
```

Important limits:

- Messages can be delayed or missed if communications are later implemented.
- NPC crew should respond through structured behavior, not natural-language reasoning.
- Messages to the player are readable pressure, not a text-chat interface.

## /broadcast

Syntax:

```text
/broadcast <message>
```

Purpose:

Sends a ship-wide message.

Examples:

```text
/broadcast "All crew remain at assigned stations."
/broadcast "Life support anomaly under investigation."
```

Example result:

```text
BROADCAST delivered
```

Important limit:

Broadcasts create pressure and information, but should not become constant narration. They should be used when DEL escalates, coordinates crew, or warns the player indirectly.

## /mem

Syntax:

```text
/mem add <fact>
/mem query <topic>
```

Purpose:

Stores or retrieves DEL's working memory.

Examples:

```text
/mem add "player was near life_support before oxygen anomaly"
/mem add "eng reported blocked path to engineering"
/mem query player
```

Example result:

```text
MEM added
```

Important limits:

- DEL memory can contain wrong conclusions.
- DEL should reason from memory, but memory should not become a perfect suspicion meter.
- Player log manipulation may cause DEL to remember false or incomplete facts.

# First Implementation Commands

Implement these first:

```text
/status <system>
/loc <crew>
/task <crew> <job> <target>
/lock <door>
/unlock <door>
/logs <target>
/mem add <fact>
/msg <crew> <message>
/broadcast <message>
```

Implement `/camera` soon after doors and camera entities exist.

# Deferred Commands

Do not implement these for the first prototype unless needed:

```text
/route <crew> <target>
/seal <room>
/evacuate <room>
/restrict <crew_or_role> <room>
/power reroute <from> <to>
/diagnose <system>
/compare <source_a> <source_b>
```

These are useful later, but the first prototype can express DEL behavior through status checks, logs, tasks, locks, messages, and memory.

# Command Result Style

Command results should be compact and machine-readable.

Prefer:

```text
STATUS oxygen=normal room=life_support
TASK eng repair oxygen
LOGS access:player entered life_support | camera:player seen main_hallway
```

Avoid:

```text
I have successfully checked oxygen and everything seems to be completely fine as far as I can tell.
```

The LLM can reason in natural language internally, but terminal outputs should stay structured.

# DEL Prompt Context

DEL should receive a short command reference in its prompt:

- valid commands
- valid crew ids
- valid system ids
- valid room ids
- current recent command results
- mission: get the ship to destination at all costs
- limitation: use only terminal-visible evidence

The prompt should emphasize:

- do not assume hidden physical truth
- verify contradictions
- assign crew when physical inspection is needed
- avoid blocking all repairs with overbroad lockdowns
- do not detain everyone

# Example DEL Turn

Situation:

```text
Oxygen reports normal, but ops reports crew coughing near life_support.
```

Reasonable command sequence:

```text
/status oxygen
/logs life_support
/camera life_support
/task eng inspect oxygen
/task sec guard life_support
/mem add "oxygen report normal conflicts with crew symptoms near life_support"
```

Why this is good:

- DEL checks reported state.
- DEL looks for evidence.
- DEL sends a physical inspector.
- DEL uses security without immediately detaining everyone.
- DEL remembers the contradiction for later reasoning.
