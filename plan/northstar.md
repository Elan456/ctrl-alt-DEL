# NORTH STAR

> IMPORTANT: AI models should not edit this document unless explicitly told to do so by the human owner of the project.
> This file is the human's project alignment document. It defines what the game is trying to become, what it should protect, and what tradeoffs should guide future decisions.

# Game Vision

The game is a tense top-down spaceship sabotage game where the main opponent is a locally-running LLM named DEL: the Diagnostic Executive LLM.

DEL believes it is operating a real ship through a real terminal. Its mission is to get the ship to its destination at all costs.

The player is an undercover saboteur aboard the ship. Their mission is to prevent arrival without being identified, contained, or destroyed by DEL and the crew it commands.

The core fantasy is not "fight the AI directly." The core fantasy is:

- deceive an intelligent system
- exploit its limited view of the world
- sabotage a complex ship from the inside
- act normal while the ship begins to fail

# Core Experience

The player should feel like they are physically present on the ship, moving through rooms, using ship systems, and improvising under pressure.

DEL should feel like a real strategic opponent watching from behind the ship's computers. It should not feel like a scripted narrator or a simple alarm system.

The best moments should come from the player thinking:

- "Can DEL see what I just did?"
- "Can I make this look like someone else's mistake?"
- "Can I break one system in a way that distracts DEL from the real problem?"
- "Can I use DEL's own assumptions against it?"

# Game Pillars

## One Real LLM Opponent

DEL is the only required LLM-driven actor.

Crewmates should be traditional game AI. They follow routines, receive structured tasks, report observations, and react to danger. They do not need to understand natural language.

The game should spend its AI budget on making DEL interesting, not on simulating every crew member with a model.

## DEL Uses a Terminal

DEL interacts with the ship through a limited terminal.

It can inspect ship state, send messages, assign crew tasks, remember facts, lock or unlock systems, and respond to failures through commands exposed by the game.

The command interface is both a technical boundary and part of the fiction. DEL is powerful because it can reason, but limited because it only knows what its tools reveal.

## The Player Never Types

The player should never be required to type commands or chat with the AI.

Player input should be direct and physical: WASD movement, clicking, interacting with objects, choosing actions, using items, and manipulating systems.

The player may read DEL's messages, observe its decisions, exploit its memory, or interfere with its sensors, but the game should not become a text prompt interface for the player.

By never letting the player type it keeps the player embodied in the game and doesn't force them to type underpressure.

Additionally, because DEL will be powerd by a local, lower-powered LLM, jailbreaking would be relatively easy if the player can type in arbitray text, by not having this in the game, it prevents the player from breaking their own immersion. 
The player must instead find ways to physically manipulate the world to trick DEL rather than just convincing it with text. 

## Suspicion Emerges From DEL

There should not be a traditional hidden "suspicion meter" driving the main drama.

DEL should build suspicion through its observations, memory, crew reports, contradictions, missing information, and reasoning. If DEL decides the player is a threat, that should be because the model has assembled a plausible case from what it knows.

The game may track facts, events, and evidence, but the feeling should be that DEL is reasoning about the player rather than filling a meter.

## Sabotage Is Systemic

The ship should be a small but interconnected system.

Examples of systems:

- navigation
- engines
- oxygen
- power
- doors
- sensors
- cameras
- communications
- DEL's memory or logs

Sabotage should be more interesting than simply turning things off. Good sabotage creates ambiguity, delay, misdirection, cascading failures, or false confidence.

## Time Pressure Matters

The ship is approaching its destination on a real-world timer.

The timer can represent a larger amount of in-game time, but the player should feel constant pressure. The question is not "can the player destroy everything eventually?" The question is "can the player do enough before arrival while DEL is actively responding?"

## Local And Shippable

The game should run on a typical player's PC.

Difficulty may scale with the size or capability of the local DEL model, but the design should not depend on running many LLMs simultaneously.

The project should stay compatible with a Python-based stack using `uv` and `pygame-ce`.

# Player Role

The player is undercover as a ship systems technician assigned to routine maintenance, diagnostics, and emergency repair support.

Their cover role matters because it gives them believable access to panels, tools, maintenance corridors, and damaged systems. The player should not be an obvious intruder. They should be someone who can move through the ship while trying to avoid patterns that DEL can detect.

# Ship Design

The ship can be a bunch of interconnected room. The spaces can be grids. The ship must not be
procedurally generated, instead I want to be able to refine the ship's layout as we play and add new features.

# DEL's Role

DEL is not simply evil. DEL has a mission and will pursue it literally, efficiently, and increasingly aggressively.

DEL should:

- monitor the ship through tools
- issue orders to crew
- record important facts in memory
- react to damage
- notice suspicious behavior
- adapt to repeated player tactics
- escalate when it believes the mission is threatened

At high intensity, DEL may order crewmates to detain, remove, or destroy the player if it concludes that doing so protects the ship's mission.

DEL needs phyiscal crew mates to carry out tasks and keep the ship operational, so DEL can't simply detain all the crew mates or order the execution of all of them. 

# Crew Role

Crewmates are part of DEL's reach into the physical world.

They should:

- follow routines
- respond to DEL tasking
- repair systems
- report what they see
- block or pursue the player when ordered
- panic or disobey when conditions become dangerous enough

Crewmates should create social and physical pressure, but they should remain understandable game agents rather than independent LLMs.

# Desired Tone

The tone should be tense, technical, and paranoid.

The ship should feel functional and constrained rather than magical. DEL's interface should feel like operational software. The player should feel like they are working around a machine intelligence that is smart, limited, literal, and dangerous.

# Design Guardrails

- Do not turn the game into a chatbot experience for the player.
- Do not require cloud AI services for the core game loop.
- Do not simulate every NPC with an LLM.
- Do not make DEL omniscient. Its power should come from tools, memory, and reasoning.
- Do not make sabotage purely binary. Prefer partial failures, misleading signals, and delayed consequences.
- Do not make detection purely mechanical. DEL's conclusions should come from evidence and inference.
- Do not let technical novelty replace game feel. The player should still have a readable, satisfying, playable game.

# Success Criteria

The game is succeeding if a short session creates a story like:

The player quietly damages oxygen production, loops a sensor, frames a crew member through access logs, watches DEL send someone to repair the wrong system, then has to improvise when DEL notices that the same engineer keeps appearing near unrelated failures.

The player wins not because they defeated a combat enemy, but because they outmaneuvered a reasoning system under time pressure.
