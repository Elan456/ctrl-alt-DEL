# AGENTS.md

Guidance for AI coding agents working on this project.

# Read First

Before making design or implementation changes, read:

- `plan/northstar.md` for the project vision and non-negotiable design guardrails.
- `plan/roles.md` for the locked prototype crew roster.
- `plan/systems.md` for ship systems, interconnections, DEL actions, and crew interactions.
- `plan/implementation.md` for the current code map, runtime flow, and extension checklist.
- `plan/DEL.md` for the current DEL structured action interface.

Do not edit `plan/northstar.md` unless the human owner explicitly asks you to. It is the alignment document, not a scratchpad.

# Project Summary

This is a top-down spaceship sabotage game.

The player is an undercover saboteur aboard a ship controlled by DEL, the Diagnostic Executive LLM. DEL is a locally running LLM that believes it is operating a real ship through operational software. DEL's mission is to get the ship to its destination at all costs.

The player's fantasy is not direct combat with an AI. The fantasy is:

- deceive an intelligent system
- exploit its limited view of the ship
- sabotage interconnected systems from inside the ship
- act normal while failures cascade

# Environment

uv can be found at `~/.local/bin/uv`

`llama-cpp-python` is a required dependency, not an optional extra. DEL uses the local Qwen GGUF through llama.cpp. If the model is missing, startup downloads `Qwen3-8B-Q4_K_M.gguf` from `Qwen/Qwen3-8B-GGUF` into `models/`. The `models/` directory is gitignored and should not be committed.

# Prototype Scope

Keep the first prototype small.

The prototype ship has exactly four people total:

- Player: Systems Technician
- NPC: Engineering Officer
- NPC: Operations Officer
- NPC: Security Officer

Do not add extra roles for the first prototype. If a feature seems to require a medic, captain, logistics officer, scientist, or extra technician, simplify the feature or assign the responsibility to one of the existing four roles.

The initial ship should be authored, not procedurally generated. Prefer a small layout that can be refined by hand.

Suggested first rooms:

- bridge
- engineering
- life support
- hallway
- security
- storage

Suggested first systems:

- power
- oxygen
- doors
- cameras
- DEL logs

# Core Design Rules

- DEL is the only required LLM-driven actor.
- Crew members are traditional game AI, not LLMs.
- The player never types prompts or chats with DEL.
- Player interaction should be embodied: movement, clicking, tools, items, panels, and physical actions.
- DEL uses a limited structured action interface exposed by the game.
- DEL must not be omniscient. It only knows what tools, logs, sensors, cameras, and crew reports reveal.
- DEL must never be told which crew member is the player or human-controlled character.
- Suspicion should emerge from DEL's evidence and reasoning, not from a simple hidden suspicion meter.
- Sabotage should not be a binary on/off switch. Prefer delay, ambiguity, misdirection, partial failure, false confidence, and cascading consequences.
- Technical novelty must not replace game feel. The game still needs to be readable, satisfying, and playable.

# DEL Design

DEL should feel like a strategic opponent operating from behind ship systems.

Implementation notes for DEL:

- DEL runs continuously in the background as fast as local inference completes. It does not take explicit turns and should not depend on player key presses to think.
- DEL's raw and parsed action activity is written to timestamped logs under `debug/del-transcripts/`, which is gitignored. Use those logs first when debugging DEL behavior.
- DEL returns validated Pydantic action plans. Current plans contain one to three ordered actions.
- DEL has no `status` tool. Reported system status is built into prompt context; physical truth comes through reports and other in-world evidence.
- DEL action validity is data-driven by `src/ctrl_alt_del/data/del_commands.yaml` and cross-checked against the authored ship layout, systems, doors, and crew. Invalid actions should return explicit `ERR ...` output so DEL can learn from the result.
- The arrival timer must not tick until DEL successfully executes `launch`.
- Keep DEL non-omniscient: prompts may include action-visible context such as recent action output, memory, valid action references, and time to arrival, but should not expose hidden physical truth.
- DEL prompt context, action output, reports, logs, and tool results may identify `tec` as the systems technician, but must not label `tec` or any other crew member as "player", "human", "user-controlled", or equivalent. DEL should infer suspicion from evidence, not from privileged knowledge of who the player is.

DEL can:

- inspect reported system state through prompt context
- request latest physical reports
- query locations and logs
- send messages
- assign crew tasks
- remember facts
- lock and unlock doors
- escalate when it believes the mission is threatened

DEL cannot:

- physically repair components
- know hidden physical truth by default
- see through disabled or spoofed sensors
- ignore crew pathing, panic, blocked doors, or missing tools
- solve every problem by detaining everyone

The distinction between physical truth and reported state is central. A component can be physically degraded while reporting normal if the player has spoofed or delayed the relevant evidence.

# Crew Design

Crew members are DEL's physical reach.

They should:

- follow simple routines
- respond to DEL's structured tasks
- repair systems
- inspect local conditions
- report what they see
- guard, escort, or detain when ordered
- panic or disobey when conditions become dangerous enough

They should remain readable and exploitable. They can be delayed by doors, hazards, missing parts, false alarms, or bad information.

# Player Role

The player is locked as the Ship Systems Technician for the prototype.

This role gives believable access to:

- panels
- maintenance corridors
- engineering support areas
- life support panels
- camera and sensor relays
- tools and parts

This role should create both freedom and risk. The player has reasons to touch ship systems, but repeated proximity to failures becomes evidence DEL can reason about.

# Implementation Direction

The intended stack is Python with `uv` and `pygame-ce`.

When implementation begins:

- prefer small, shippable vertical slices over broad architecture
- keep systems data-driven where practical
- make room layouts easy to author and revise
- expose DEL's abilities through explicit structured action handlers
- keep crew behavior deterministic and inspectable before adding complexity
- make evidence events structured so DEL can reason from them
- prioritize readable game feedback over hidden simulation depth
- never add confusing band-aids; when behavior changes, update names, schemas, comments, docs, tests, and error messages so the wording matches what the code actually does
- treat code readability and precise terminology as important implementation requirements

# Feature Triage

When deciding whether to add a feature, ask:

- Does this help the player deceive DEL?
- Does this exploit DEL's limited view?
- Does this create physical sabotage, misdirection, or time pressure?
- Can it work with four total crew members?
- Can it be represented through DEL's structured action tools?
- Can the player interact with it without typing?
- Is it readable to the player?

If the answer is mostly no, defer it.

# Violence And Crew Death

Do not make murder a first-prototype feature unless the human owner explicitly asks for it.

The current direction is that violence may exist later, but it should be desperate and costly, not an optimal way to remove DEL's physical agents. Non-lethal interference should come first:

- lock crew out
- lure them away
- fake orders
- steal tools
- delay repairs
- frame them
- make them evacuate or panic

# Documentation Rules

- Keep `plan/northstar.md` stable unless explicitly instructed.
- Put prototype scope decisions in focused planning docs under `plan/`.
- Prefer small, concrete docs over broad speculative documents.
- When a new decision supersedes an older planning note, update or cross-reference the older note so future agents do not revive stale scope.

# Current Priority

The project is trying to reach a playable prototype, not a complete simulation.

Bias toward:

- fewer roles
- fewer rooms
- fewer systems
- clearer interactions
- stronger evidence loops
- obvious player feedback

The target is a small pressure cooker where DEL, three NPC crew members, and the player create interesting sabotage stories under time pressure.

# Backup and Redundancy Policy

The game's code shall have no fallback or backup systems. For the prototype, all main features should work directly.
For example, if the local LLM will not load, do not add a deterministic fallback; that is wasted development effort.
