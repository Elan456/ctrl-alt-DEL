
# HISTORICAL SCRATCHPAD

This file records early raw ideas. It is not current implementation guidance.

Use these instead:

- `plan/northstar.md` for stable product direction.
- `plan/implementation.md` for the current code map.
- `plan/DEL.md` for the current structured action interface.
- `plan/systems.md` and `plan/roles.md` for prototype scope.

# Early Ideas
- the space ship is controlled by a locally-running LLM on the player's PC
- The LLM has a linux-like terminal it can interact with to issue commands 
- The LLM's job is to get the ship to it's destination at all costs
- The player is part of an underground organization and is undercover on the ship
- The player wants to ensure the ship does not make it to its destination at all costs
- The ship will arrive in some number of real-world minutes (let's say 5) it can be longer in-game time though (like each minute is an hour of game time)
- The player is onboard the ship and needs to find ways to sabotage witohut alerting the LLM
- The LLM's name could be "DEL": Diagnostic Executive LLM
- The game's difficulty could be based on the size of the DEL model. Like from 1GB to 8GB so that it can always fit on a typical gamer's PC graphics card VRAM
- The game can be a top-down grid-based space ship.
- The player moves with WASD and can interact with different systems (like oxygen production) to turn them on and off
- DEL can check the location of individual crew members using commands like `/loc 1` to get the room the crew member "1" is in. 
- DEL can write information to a scratch pad with something like `/mem "crew member 1 did not repair the oxygen production after being asked to" `
- DEL can send out global messages or directed messages with something like `/broadcast "message"` and `/msg 1 "go fix the oxygen"` to send to crew mate 1 specfically
- DEL should be prompted in a way that convinces it that the situtaion is a real ship and it is operating a real terminal. 
- The game will use Pygame-ce as the game engine
- The project with be python-based and use uv to manage it
- The player can mess with DEL's sensors in some way
- The player can mess with or even read DEL's memory if that get certain items
- The player must NEVER have to type, it should all be clicking and or WASD and or interacting. 
- The player has a "cover role" like the ship's engineer or something
- There is no discrete "suspicon meter" coded into the game. DEL simply must manage it's memory as an LLM
- DEL can order the other crewmates to remove or destroy the player
