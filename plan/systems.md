# PROTOTYPE SYSTEMS

This is the first-version systems plan. Keep it small enough to build and test with the four-person roster in `plan/roles.md`.

# Core Systems

Build only these systems first:

- power
- oxygen
- doors
- cameras
- logs

Defer navigation, engines, communications, weapons, medical systems, and detailed inventory until the first loop is playable.

The arrival timer can be a simple global countdown. It does not need a full navigation or engine simulation yet.

# Main Rule

Every system has:

- physical state: what is actually true
- reported state: what DEL can see

The fun comes from the player changing one without immediately changing the other.

Example:

```text
Oxygen physical state: degraded
Oxygen reported state: normal
Reason: player spoofed the life-support panel
```

Use simple states:

- normal
- degraded
- failed
- locked
- spoofed
- under repair

# Prototype Rooms

Use a small authored ship:

- bridge
- engineering
- life support
- security
- storage
- main hallway
- maintenance corridor

Rooms matter because location is evidence. DEL should be able to ask who was nearby, which doors opened, and what cameras or crew saw.

# Role Fit

```text
Player Systems Technician -> panels, sabotage, fake repairs, diagnostics
Engineering Officer       -> power repairs, oxygen repairs, serious fixes
Operations Officer        -> bridge status, mission timer, crew check-ins
Security Officer          -> doors, cameras, patrols, containment
DEL                       -> orders, diagnosis, locks, logs, memory
```

Do not add extra roles to support systems. If a system cannot work with these four people, it is too large for the prototype.

# Player Actions

The player never types. Use direct actions:

- inspect
- repair
- fake repair
- loosen
- jam
- reroute
- spoof
- wipe log
- forge log
- lock
- unlock

Normal technician work and sabotage should look similar from the outside. DEL should need evidence to tell the difference.

# DEL Commands

Start with a small terminal API:

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

DEL gets structured reports from these commands. It does not get hidden truth.

# Evidence

Track only the evidence needed for the prototype:

- access logs
- door events
- camera sightings
- crew reports
- repair results
- system status reports
- DEL memory entries

Rules:

- logs can be forged or wiped
- cameras can be looped or disabled
- crew reports cannot be edited once made
- physical damage remains real until repaired

# System Connections

```text
Power -> Oxygen
Power -> Doors
Power -> Cameras
Power -> Logs

Doors -> Routing
Doors -> Repair access
Doors -> Containment

Cameras -> DEL evidence
Cameras -> Security response

Oxygen -> Crew panic
Oxygen -> Emergency escalation

Logs -> Alibis
Logs -> Framing
Logs -> DEL reasoning
```

Power should create tradeoffs, not instant victory. Turning off power might disable cameras, but it can also block doors, delay the player, and make DEL escalate.

# Power

Components:

- engineering power panel
- hallway breaker
- backup battery in storage

Player sabotage:

- trip a breaker
- loosen a connection
- reroute power from one room
- fake a repair

DEL and crew response:

- DEL checks reported power status
- DEL sends the engineering officer to inspect or repair
- DEL may lock engineering if it sees repeated tampering
- the engineering officer can reset breakers or report tampering

# Oxygen

Components:

- life-support panel
- oxygen scrubber
- air quality sensor

Player sabotage:

- degrade the scrubber
- spoof the air quality sensor
- fake a repair
- create a delayed oxygen fault

DEL and crew response:

- DEL checks reported oxygen status
- DEL compares sensor status with crew reports
- DEL sends the engineering officer or player to inspect
- crew may abandon tasks or panic if oxygen gets dangerous

# Doors

Components:

- powered doors
- manual hatch
- door access panel

Player sabotage:

- jam a door
- unlock a restricted route
- lock a crew member out of a repair path
- forge or wipe a door log

DEL and crew response:

- DEL locks or unlocks doors
- DEL reviews door logs
- security can guard doors or detain a suspect
- blocked doors can delay both the player and NPC crew

# Cameras

Components:

- main hallway camera
- life support camera
- security camera console

Player sabotage:

- loop a camera
- disable a camera
- trigger false motion
- wipe a short footage window

DEL and crew response:

- DEL checks current or recent camera sightings
- DEL compares camera evidence with door logs
- security can inspect blind spots or watch an area in person

# Logs

Components:

- access log terminal
- DEL event log
- repair task records

Player sabotage:

- wipe selected entries
- forge an access entry
- alter a repair result
- plant evidence against another crew member

DEL and crew response:

- DEL reviews logs and writes memory notes
- DEL compares logs with crew reports and cameras
- crew can confirm or contradict what the logs claim

# Incident Loop

Most sabotage should follow this pattern:

1. Player changes a physical system.
2. Logs, cameras, sensors, or crew may notice.
3. DEL receives partial information.
4. DEL assigns a crew task.
5. Crew path through the ship to inspect or repair.
6. Player delays, redirects, hides, or frames.
7. Crew report the outcome.
8. DEL updates memory and escalates or de-escalates.

The best play is not always staying unseen. Sometimes it is letting DEL see the wrong thing.

# First Playable Scenario

Build one short scenario:

The player must delay arrival by causing an oxygen or power problem while avoiding containment by the security officer.

Required beats:

- one power sabotage
- one oxygen sabotage
- one camera manipulation
- one door or log manipulation
- one DEL task order to an NPC
- one chance to frame or misdirect another crew member

This proves the core game without building a full ship simulation.
