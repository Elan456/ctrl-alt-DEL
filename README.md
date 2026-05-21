# ctrl-alt-DEL

A top-down spaceship sabotage prototype.

The player is an undercover systems technician trying to stop the ship from arriving while DEL, the Diagnostic Executive LLM, diagnoses failures and commands the crew through a limited terminal interface.

## Run

This project is intended for `uv`:

```bash
uv run ctrl-alt-del
```

In this environment `uv` may not be installed yet. With dependencies installed another way, the module entry point is:

```bash
python -m ctrl_alt_del
```

## Current Shape

- `Ship` owns rooms, systems, logs, crew, and door locks.
- `CrewMate` inherits from `pygame.sprite.Sprite`.
- `DEL` owns terminal-style command handling and delegates free-form reasoning to an optional LLM backend.
- The default DEL backend is deterministic so the prototype can run without a local model.
