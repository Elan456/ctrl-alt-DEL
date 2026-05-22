# ctrl-alt-DEL

A top-down spaceship sabotage prototype.

The player is an undercover systems technician trying to stop the ship from arriving while DEL, the Diagnostic Executive LLM, diagnoses failures and commands the crew through a limited structured action interface.

## Run

This project is intended for `uv`:

```bash
uv run play
```

DEL requires a `llama-cpp-python` build with GPU offload support. This project configures `uv` to
build `llama-cpp-python` from source with CUDA enabled, using `nvcc` and GCC 15 as the CUDA host
compiler. If an older CPU-only build is already installed in `.venv`, rebuild it once:

```bash
scripts/install-gpu.sh
```

In this environment `uv` may not be installed yet. With dependencies installed another way, the module entry point is:

```bash
python -m ctrl_alt_del
```

`uv run play` writes DEL's action transcript to `debug/del-transcripts/` with a timestamped filename and opens a second terminal that tails it. If no terminal emulator is available, the game prints the transcript path instead. Set `CTRL_ALT_DEL_NO_TERMINAL=1` to disable the extra terminal.

DEL uses Qwen's `Qwen3-8B-Q4_K_M.gguf` through `llama-cpp-python`. If the GGUF is missing, startup downloads it from `Qwen/Qwen3-8B-GGUF` into `models/`. Set `CTRL_ALT_DEL_MODEL_PATH` to use or download to a different path. If `llama-cpp-python` does not report GPU offload support, startup fails with setup guidance instead of running DEL on CPU.

## Current Shape

- `Ship` owns authored rooms, systems, logs, crew, pathing, door locks, and the arrival timer.
- `CrewMate` inherits from `pygame.sprite.Sprite` and implements deterministic NPC task behavior.
- `DEL` is the only LLM-driven actor. It runs continuously in the background and executes validated structured action plans.
- DEL can emit one to three ordered actions per inference pass.
- The arrival timer does not start until DEL executes `launch`.
- DEL does not have a `status` action; visible reported system status is built into its prompt.
- DEL action schema lives in `src/ctrl_alt_del/del_ai/actions.py`; stateful execution lives in `src/ctrl_alt_del/del_ai/commands.py`.
- Role and target validation is defined in `src/ctrl_alt_del/data/del_commands.yaml` and checked against loaded ship rooms, doors, systems, and crew.

## Documentation Map

- `AGENTS.md`: rules for AI coding agents.
- `plan/northstar.md`: stable product vision and design guardrails. Do not edit unless explicitly asked.
- `plan/implementation.md`: current code map and extension checklist.
- `plan/DEL.md`: DEL action interface, prompt visibility, and examples.
- `plan/roles.md`: locked four-person prototype roster.
- `plan/systems.md`: prototype systems, evidence loop, and first playable scenario.
- `plan/start.md`: historical scratchpad only; do not treat it as current scope.
