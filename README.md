# ctrl-alt-DEL

A top-down spaceship sabotage prototype.

The player is an undercover systems technician trying to stop the ship from arriving while DEL, the Diagnostic Executive LLM, diagnoses failures and commands the crew through a limited terminal interface.

## Run

This project is intended for `uv`:

```bash
uv run play
```

In this environment `uv` may not be installed yet. With dependencies installed another way, the module entry point is:

```bash
python -m ctrl_alt_del
```

`uv run play` writes DEL's ship-terminal transcript to `debug/del-transcripts/` with a timestamped filename and opens a second terminal that tails it. If no terminal emulator is available, the game prints the transcript path instead. Set `CTRL_ALT_DEL_NO_TERMINAL=1` to disable the extra terminal.

DEL uses Qwen's `Qwen3-8B-Q4_K_M.gguf` through `llama-cpp-python`. If the GGUF is missing, startup downloads it from `Qwen/Qwen3-8B-GGUF` into `models/`. Set `CTRL_ALT_DEL_MODEL_PATH` to use or download to a different path.

## Current Shape

- `Ship` owns rooms, systems, logs, crew, and door locks.
- `CrewMate` inherits from `pygame.sprite.Sprite`.
- `DEL` owns terminal-style command handling and requires the local Qwen backend for free-form reasoning.
- DEL runs inference continuously in the background and executes terminal commands as it produces them.
- DEL command validation is defined in `src/ctrl_alt_del/data/del_commands.yaml` and checked against the loaded ship rooms, doors, systems, and crew.
