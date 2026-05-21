# PROTOTYPE CREW ROLES

The prototype ship has exactly four crew members total:

- one player character
- three NPC crew members

Do not add more roles for the first prototype. More people make DEL's reasoning, crew pathing, reports, schedules, and suspicion harder to build and harder to read. The first version should prove the core loop with a tiny cast.

# Crew Roster

## 1. Player: Systems Technician

The player is undercover as the ship systems technician.

Primary access:

- maintenance corridors
- engineering support panels
- life support panels
- camera and sensor relays
- storage

Normal behavior:

- inspecting panels
- carrying tools or parts
- responding to repair tasks
- running diagnostics
- moving between engineering, life support, storage, and security relay areas

Suspicious behavior:

- ignoring assigned repairs
- appearing near unrelated failures
- entering the bridge without a task
- editing logs
- disabling cameras or sensors before failures
- carrying restricted parts without a work order

Gameplay purpose:

- lets the player touch the ship's systems without being an obvious intruder
- creates natural alibis for sabotage
- gives DEL a reason to watch the player closely when failures cluster around maintenance work

## 2. NPC: Engineering Officer

The engineering officer is responsible for power, engines, and serious mechanical repairs.

Primary access:

- engineering
- reactor or power room
- engine control
- storage
- maintenance corridors

Normal behavior:

- checking power load
- repairing breakers and junctions
- inspecting engine faults
- fetching parts from storage
- responding to DEL's high-priority repair orders

DEL can order them to:

- repair power failures
- inspect engine control
- reset breakers
- carry replacement parts
- verify whether the player completed a repair correctly

Gameplay purpose:

- gives DEL a competent repair actor besides the player
- creates pressure when the player sabotages power or engines
- can expose fake repairs if they inspect the same component later

Weaknesses:

- can be delayed by locked doors, missing parts, bad routing, or false diagnostics
- may focus on obvious mechanical failures while missing sensor or log manipulation

## 3. NPC: Operations Officer

The operations officer is responsible for navigation, communications, and mission coordination.

Primary access:

- bridge
- communications console
- navigation console
- security checkpoint if ordered
- main hallway

Normal behavior:

- monitoring course status
- acknowledging DEL broadcasts
- checking communications
- reporting mission-impacting failures
- staying near the bridge unless reassigned

DEL can order them to:

- verify navigation confidence
- send or confirm messages
- inspect communications failures
- report crew check-ins
- initiate emergency procedures from the bridge

Gameplay purpose:

- protects the arrival timer and mission objective
- gives DEL a bridge-side witness
- makes navigation and communications sabotage matter quickly

Weaknesses:

- has limited mechanical repair skill
- depends heavily on reported data
- can be misled by spoofed sensors, delayed messages, or forged confirmations

## 4. NPC: Security Officer

The security officer is responsible for cameras, doors, patrols, and containment.

Primary access:

- security room
- camera console
- door control console
- main hallway
- restricted areas when DEL authorizes it

Normal behavior:

- patrolling central routes
- checking camera alerts
- responding to unauthorized access
- guarding restricted rooms during emergencies
- escorting or detaining crew when DEL orders it

DEL can order them to:

- guard a room
- escort the player
- detain a suspect
- inspect camera tampering
- verify a blind spot in person
- control access during lockdown

Gameplay purpose:

- gives DEL a physical enforcement tool
- makes cameras and doors matter
- creates the main threat once DEL suspects the player

Weaknesses:

- can be drawn away by false alarms
- can be blocked by doors or hazards
- cannot repair most systems
- may rely too much on camera evidence that the player can manipulate

# Role Coverage

The four roles cover the prototype systems without creating a large cast:

```text
Systems Technician -> player verbs, sabotage, fake repairs, panels
Engineering Officer -> power, engines, serious repairs
Operations Officer -> navigation, communications, bridge reports
Security Officer -> cameras, doors, patrols, containment
DEL -> reasoning, orders, memory, locks, diagnosis
```

Oxygen is intentionally shared:

- the player can access life support panels
- the engineering officer can perform serious repairs
- the operations officer can report mission risk
- the security officer can enforce evacuation or lockdown
- DEL decides who to send based on evidence and urgency

# Starting Positions

Suggested starting positions:

- player: maintenance corridor or engineering support
- engineering officer: engineering
- operations officer: bridge
- security officer: security room or main hallway

This creates immediate map coverage while keeping the crew readable.

# Prototype Rule

For the first prototype, every crew behavior should be expressible through these four roles.

If a feature seems to require a medic, logistics officer, captain, scientist, or extra technician, simplify the feature or assign the responsibility to one of the existing roles.

The goal is not a complete ship organization. The goal is a small pressure cooker where every person matters.
