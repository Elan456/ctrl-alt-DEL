# ON-BOARD SYSTEMS PLAN

This document describes the ship systems, how they depend on each other, and how DEL and crew members can interact with them.

The goal is not to simulate a realistic spacecraft in exhaustive detail. The goal is to create a small, readable, interconnected machine that gives the player many ways to sabotage, misdirect, delay, and improvise.

# Design Goals

- Every important system should have physical locations the player can visit.
- Every important system should have a reported state that DEL can inspect.
- Physical truth and reported state should sometimes diverge.
- Sabotage should usually create a problem, an explanation, and evidence.
- DEL should be powerful at diagnosis, but limited by sensors, logs, crew reports, and tool output.
- Crew members should be the hands of DEL, not independent strategic masterminds.
- Repair should take time, require pathing through the ship, and sometimes require parts or access.
- The player should often have to choose between damaging the ship and maintaining a believable cover routine.

# Core Model

## Rooms

The ship is built from authored rooms connected by doors, vents, corridors, and restricted passages.

Each room can contain:

- one or more ship components
- doors or hatches
- cameras or local sensors
- access panels
- storage lockers
- crew workstations
- environmental hazards

Rooms should matter because location is evidence. A system failure is more interesting when DEL can ask who was nearby, which doors opened, which camera saw movement, and which crew member had legitimate reason to be there.

## Components

A component is a physical object that belongs to a system.

Examples:

- oxygen scrubber
- engine coolant pump
- navigation computer
- camera relay
- door controller
- power junction
- communications antenna servo
- DEL memory bank

Each component should have:

- a room location
- a physical condition
- a reported condition
- interaction actions
- repair requirements
- logs or evidence it can create

## Resources

Systems exchange a small set of resources:

- power
- air
- heat
- data
- thrust
- navigation confidence
- access authority

Keeping the resource list short makes the game easier to read while still allowing cascading failures.

## Signals And Evidence

Events should leave evidence through structured channels:

- access logs
- camera sightings
- crew reports
- sensor readings
- component diagnostics
- DEL memory entries
- door open/close events
- repair task results

The player should be able to create, destroy, delay, spoof, or redirect some evidence, but not all evidence.

# System Graph

The first playable ship should use a compact dependency graph:

```text
Power
  -> Oxygen
  -> Doors
  -> Cameras
  -> Sensors
  -> Communications
  -> Navigation
  -> Engine Control
  -> DEL Core

Sensors
  -> Navigation confidence
  -> DEL situational awareness
  -> Crew task targeting

Cameras
  -> DEL visual evidence
  -> Crew location verification

Doors
  -> Crew routing
  -> Player routing
  -> Containment
  -> Repair access

Oxygen
  -> Crew safety
  -> Panic and disobedience
  -> Time pressure

Engine Control
  -> Arrival progress
  -> Heat buildup
  -> Power load

Navigation
  -> Arrival accuracy
  -> Course corrections
  -> DEL mission confidence

Communications
  -> Crew-wide orders
  -> Emergency beacons
  -> Remote destination updates

DEL Core
  -> Command authority
  -> Memory
  -> Diagnosis
  -> System locks
```

Power should be the main dependency, but it should not be the only interesting target. If power is always the best sabotage, the rest of the ship becomes decoration.

# Shared System States

Each major system should use readable states rather than hidden numeric complexity.

Suggested states:

- normal
- degraded
- unstable
- failed
- isolated
- locked
- spoofed
- under repair

Systems may also have a hidden physical state and a visible reported state.

Example:

```text
Oxygen physical state: degraded
Oxygen reported state: normal
Reason: sensor feed is spoofed
```

This distinction is central to the game. DEL should be able to reason from reported state, but the player can attack the reporting layer.

# Player Interactions

The player never types. System interactions should be direct physical actions chosen from context menus, tools, or item use.

Useful action verbs:

- inspect
- loosen
- swap
- jam
- bypass
- reroute
- overload
- contaminate
- spoof
- wipe
- forge
- plant
- lock
- unlock
- repair
- fake repair

Different cover roles should make different actions look normal.

Examples:

- An engineer can open power panels without immediately looking suspicious.
- A medic can enter life-support rooms during oxygen incidents.
- A logistics officer can move parts, tools, and sealed containers.
- A technician can access cameras, relays, and diagnostics.

# DEL Interactions

DEL interacts with systems only through terminal commands exposed by the game. Commands should return structured, limited information.

DEL should never receive omniscient truth by default. It should see what the ship reports, what logs record, what cameras observe, and what crew members tell it.

## Example Command Categories

Inspection:

```text
/status oxygen
/status power
/status navigation
/diag component O2_SCRUBBER_A
/room engineering
/loc crew_03
/near O2_SCRUBBER_A
```

Orders:

```text
/task crew_02 repair O2_SCRUBBER_A
/task crew_04 inspect NAV_COMPUTER
/task crew_01 escort player
/task crew_03 guard engineering
```

Authority:

```text
/lock door D_12
/unlock door D_12
/restrict role engineer engine_control
/isolate power_junction PWR_J_03
```

Messaging:

```text
/broadcast "All crew report to assigned stations."
/msg crew_02 "Inspect the oxygen scrubber and report abnormalities."
```

Memory:

```text
/mem add "crew_03 failed to repair oxygen after being tasked."
/mem query "recent oxygen incidents"
/mem tag player suspicious_near_failures
```

Evidence Review:

```text
/logs access engineering last_5_min
/logs doors D_10 last_5_min
/camera CAM_04 last_30_sec
/reports recent
```

## DEL Limits

DEL should be able to make strong inferences, but only from available evidence.

Important limits:

- Cameras have blind spots.
- Sensors can be stale, spoofed, or offline.
- Crew reports can be late, incomplete, or wrong.
- Logs can be wiped, forged, or contradicted.
- Locked doors can delay crew as well as the player.
- DEL cannot physically repair components.
- DEL cannot order every crew member to detain everyone without risking the mission.

# Crew Interactions

Crew members are traditional game AI. They follow routines, receive tasks, and report observations.

Each crew member should have:

- name or id
- role
- normal route
- authorized rooms
- skill tags
- current task
- fear or stress level
- loyalty to DEL
- last seen facts

## Crew Task Types

Repair:

- go to component
- inspect local state
- fetch required part if needed
- perform timed repair
- report success, failure, or obstruction

Inspection:

- go to room or component
- observe visible state
- report anomalies, nearby crew, blocked access, or hazards

Guard:

- stand near a room, door, or component
- challenge unauthorized crew
- report suspicious movement

Escort:

- follow a crew member
- guide or force them to a target room
- report if they flee or enter restricted areas

Evacuate:

- leave dangerous room
- move to safe zone
- stop performing non-critical repairs

Manual Operation:

- hold a physical switch
- crank a door
- restart a local machine
- bypass a failed controller

## Crew Limits

Crew members should remain understandable and exploitable.

- They do not know hidden truth.
- They can be delayed by doors, hazards, bad orders, or missing tools.
- They may panic when oxygen, heat, or alarms become severe.
- They can misidentify causes.
- They can report the player if they directly witness suspicious behavior.
- They can be framed by forged logs or suspicious proximity.

# Major Systems

## Power

Purpose:

Power feeds most other systems and controls how much the ship can do at once.

Components:

- reactor
- battery banks
- power junctions
- room breakers
- emergency backup cells

Dependencies:

- none for primary generation
- cooling may be needed to avoid instability

Affects:

- oxygen
- doors
- cameras
- sensors
- navigation
- engine control
- communications
- DEL core

Player sabotage:

- overload a junction
- trip a breaker
- drain a battery
- reroute power away from a critical system
- create intermittent brownouts
- make a junction report normal while output is degraded

DEL actions:

- inspect power status
- isolate a junction
- reroute power
- order repairs
- lock access to power rooms

Crew actions:

- reset breakers
- replace fuses
- inspect junctions
- carry backup cells
- manually restore local power

Fun connections:

- Power failures can disable cameras, creating opportunities.
- Restoring power can also restore evidence sources.
- Rerouted power can make another system fail later.

## Oxygen

Purpose:

Oxygen keeps crew alive and calm.

Components:

- oxygen scrubbers
- tanks
- vents
- pressure doors
- air quality sensors

Dependencies:

- power
- vents or ducts

Affects:

- crew panic
- crew task reliability
- room accessibility
- emergency escalation

Player sabotage:

- contaminate scrubber filters
- partially close a vent
- spoof air quality sensors
- drain a local tank
- create a slow leak
- fake a completed repair

DEL actions:

- check oxygen status
- compare room air reports
- order crew to inspect scrubbers
- seal rooms
- evacuate crew

Crew actions:

- replace filters
- inspect leaks
- carry emergency tanks
- manually seal a room
- report symptoms or bad air

Fun connections:

- A spoofed sensor can keep DEL calm while crew members in the room begin to react.
- Low oxygen can cause crews to abandon guard posts.
- Sealing a leak may trap someone or block a route.

## Doors And Access

Purpose:

Doors control movement, containment, repair access, and alibis.

Components:

- powered doors
- manual hatches
- access readers
- door controllers
- emergency bulkheads

Dependencies:

- power for normal operation
- access authority for restricted doors

Affects:

- pathing
- crew response time
- player escape options
- DEL containment options

Player sabotage:

- jam a door
- spoof an access reader
- open a restricted path
- lock a crew member out of a repair route
- create a fake access log
- wipe an inconvenient door event

DEL actions:

- lock or unlock doors
- restrict access by role
- review door logs
- contain a suspect
- open repair routes for crew

Crew actions:

- use authorized doors
- force manual hatches slowly
- report blocked paths
- guard doors

Fun connections:

- DEL can trap the player, but the same lockdown can block repair crews.
- Door logs are strong evidence but also a strong framing tool.
- Manual hatches create slow, risky alternate routes.

## Sensors

Purpose:

Sensors tell DEL what the ship thinks is happening.

Components:

- temperature sensors
- pressure sensors
- air quality sensors
- vibration sensors
- system diagnostic probes
- sensor relay nodes

Dependencies:

- power
- data relay

Affects:

- DEL diagnosis
- navigation confidence
- crew task targeting
- alarm generation

Player sabotage:

- spoof a reading
- disconnect a probe
- delay relay updates
- make a failure look like noise
- redirect one sensor's value into another channel

DEL actions:

- query readings
- compare sensor contradictions
- request local crew inspection
- mark sensors unreliable
- switch to backup readings

Crew actions:

- inspect sensor hardware
- calibrate probes
- confirm physical conditions
- replace relay modules

Fun connections:

- Sensor sabotage is not directly destructive, but it changes DEL's beliefs.
- Contradictory sensors should make DEL curious rather than instantly correct.
- Crew inspection can pierce spoofing if the player lets them reach the site.

## Cameras

Purpose:

Cameras provide visual evidence and make movement risky.

Components:

- cameras
- camera relays
- storage buffer
- monitor station

Dependencies:

- power
- data relay

Affects:

- DEL evidence
- player route planning
- crew verification

Player sabotage:

- loop a camera
- create static
- rotate a camera away
- wipe recent footage
- cut a camera relay
- trigger a false motion event

DEL actions:

- review recent footage
- check current camera view
- compare camera coverage with access logs
- order camera relay repair

Crew actions:

- inspect camera hardware
- restore relay power
- report tampering
- physically watch a blind spot

Fun connections:

- Cameras should have visible cones or readable coverage.
- A looped camera can create confidence that is wrong.
- Destroying cameras removes evidence but is itself suspicious.

## Navigation

Purpose:

Navigation determines whether the ship will arrive correctly.

Components:

- navigation computer
- star tracker
- inertial unit
- course database
- correction scheduler

Dependencies:

- power
- sensors
- engine control

Affects:

- arrival timer
- destination accuracy
- DEL mission confidence

Player sabotage:

- corrupt course data
- delay a correction
- spoof a star tracker
- create small accumulating drift
- force a recalibration at a bad time

DEL actions:

- check course confidence
- order recalibration
- compare redundant navigation sources
- prioritize engine correction
- protect navigation rooms

Crew actions:

- run local calibration
- inspect star tracker hardware
- manually verify course data
- replace nav modules

Fun connections:

- Navigation sabotage should often be subtle and delayed.
- DEL may not notice until the ship is already meaningfully off course.
- Navigation failures create mission panic without necessarily killing crew.

## Engine Control

Purpose:

Engine control moves the arrival timer forward and converts navigation decisions into thrust.

Components:

- engine controller
- thrust valves
- coolant pump
- ignition sequencer
- heat vents

Dependencies:

- power
- navigation
- cooling

Affects:

- arrival progress
- heat
- power load
- emergency risk

Player sabotage:

- misalign thrust valves
- overheat a coolant pump
- delay ignition cycles
- cause inefficient burns
- create intermittent controller faults

DEL actions:

- inspect engine status
- reduce thrust to protect ship
- increase thrust to recover time
- order coolant repair
- lock engine rooms

Crew actions:

- repair coolant
- reset controller faults
- manually align valves
- report heat or vibration

Fun connections:

- DEL can recover from some sabotage by pushing engines harder, creating new risks.
- Engine work is noisy and dangerous, so it creates believable reasons for crew movement.
- A small engine fault can distract from a larger navigation attack.

## Communications

Purpose:

Communications allow ship-wide orders, emergency signals, and mission updates.

Components:

- internal comm relay
- external antenna
- broadcast console
- message buffer

Dependencies:

- power
- data relay

Affects:

- DEL order reach
- crew coordination
- emergency broadcasts
- outside mission status

Player sabotage:

- jam internal comms in one section
- delay outgoing messages
- alter a queued message
- disable external antenna alignment
- create false delivery confirmations

DEL actions:

- broadcast orders
- send direct messages
- verify message delivery
- request crew acknowledgement
- send emergency beacon

Crew actions:

- acknowledge orders
- repair relays
- carry verbal messages if comms fail
- inspect antenna hardware

Fun connections:

- Broken comms make DEL less coordinated but can make crew behave unpredictably.
- A false acknowledgement can send DEL's plan down the wrong path.
- Verbal message carrying gives the player a physical target to delay.

## DEL Core, Memory, And Logs

Purpose:

DEL's core provides reasoning, command authority, memory, and operational continuity.

Components:

- terminal interface
- command router
- memory bank
- event log
- diagnostic database
- authority module

Dependencies:

- power
- data relay
- storage integrity

Affects:

- DEL decision quality
- command speed
- suspicion reasoning
- evidence durability
- system locks

Player sabotage:

- read memory with the right access
- wipe selected logs
- forge access entries
- corrupt a diagnostic database
- delay event ingestion
- plant misleading evidence
- cut DEL off from one system channel

DEL actions:

- query memory
- write memory
- review logs
- cross-check evidence
- lock critical systems
- restrict crew privileges

Crew actions:

- reboot local terminals
- replace storage modules
- report terminal errors
- guard DEL access rooms

Fun connections:

- Attacking DEL directly should be powerful but risky.
- Wiping all logs is suspicious; editing one log is more interesting.
- DEL memory should sometimes preserve wrong conclusions that the player can exploit later.

# Repair And Response Flow

System incidents should generally follow this loop:

1. A component changes physical state.
2. Sensors, logs, cameras, or crew may notice.
3. DEL receives partial information.
4. DEL diagnoses and assigns a response.
5. Crew path to the target if possible.
6. The player can delay, redirect, frame, or compound the response.
7. Crew report an outcome.
8. DEL updates memory and escalates or de-escalates.

The player should be able to interfere at several points in this chain. The best play should not always be preventing detection. Sometimes it should be allowing detection with the wrong explanation.

# Misdirection Patterns

Useful recurring patterns:

- Break one system, spoof another system to hide the break.
- Cause a small obvious failure to cover a subtle delayed failure.
- Lock a door to delay repair, then make the lock look like DEL's own containment order.
- Forge access logs to put another crew member near the failure.
- Create contradictory evidence so DEL wastes time verifying.
- Trigger a real emergency that gives the player's cover role a reason to enter restricted rooms.
- Damage communications so DEL's correct order arrives too late.
- Restore a system just enough to make DEL trust a false report.

# Prototype Slice

The first implementation should avoid too many systems at once.

Recommended first slice:

- rooms: bridge, engineering, life support, hallway, security, storage
- systems: power, oxygen, doors, cameras, DEL logs
- crew: four total people: player systems technician, engineering officer, operations officer, security officer
- DEL commands: status, loc, task, lock, unlock, logs, mem, msg, broadcast
- player tools: wrench, access card, log editor, camera loop device
- win path: delay arrival by causing oxygen or power disruption while avoiding containment
- advanced path: frame a crew member or make DEL send repair crew to the wrong component

This slice is small enough to build, but it includes the core promise: physical sabotage, limited observation, crew tasking, DEL reasoning, and misdirection.

# Open Design Questions

- Should each cover role have a unique starting tool?
- Can the player change clothes, badges, or apparent role during a run?
- How much can DEL remember across runs, if anything?
- Should crew members have personal trust levels with the player?
- Should the player be able to save a crew member to preserve cover or create an ally?
- How visible should DEL's memory be to the player by default?
- What is the minimum amount of text DEL can output while still feeling intelligent?
