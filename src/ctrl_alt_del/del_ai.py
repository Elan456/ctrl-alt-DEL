from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ctrl_alt_del.ship import Ship


class LLMBackend(Protocol):
    """Backend boundary for local LLM packages."""

    def complete(self, prompt: str) -> str:
        raise NotImplementedError


class DeterministicBackend:
    """Safe default while the game loop is being built."""

    def complete(self, prompt: str) -> str:
        return "Continue diagnosis. Query status, compare logs, and assign crew conservatively."


class LlamaCppBackend:
    """Optional llama-cpp-python adapter.

    Install with `uv sync --extra llm` once uv is available. This class imports
    lazily so the prototype can run without a local model or native build.
    """

    def __init__(self, model_path: str, max_tokens: int = 128) -> None:
        from llama_cpp import Llama

        self._llm = Llama(model_path=model_path)
        self._max_tokens = max_tokens

    def complete(self, prompt: str) -> str:
        result = self._llm(prompt, max_tokens=self._max_tokens, stop=["\n\n"])
        return str(result["choices"][0]["text"]).strip()


@dataclass
class DEL:
    """Diagnostic Executive LLM facade and terminal command surface."""

    ship: Ship
    backend: LLMBackend = field(default_factory=DeterministicBackend)
    memory: list[str] = field(default_factory=list)

    def think(self) -> str:
        prompt = self._build_prompt()
        thought = self.backend.complete(prompt)
        self.memory.append(thought)
        return thought

    def execute(self, command_line: str) -> str:
        parts = command_line.strip().split()
        if not parts:
            return "ERR empty command"

        command = parts[0]
        args = parts[1:]

        try:
            if command == "/status":
                return self._status(args)
            if command == "/loc":
                return self._loc(args)
            if command == "/task":
                return self._task(args)
            if command == "/lock":
                return self._lock(args)
            if command == "/unlock":
                return self._unlock(args)
            if command == "/logs":
                return self._logs(args)
            if command == "/mem":
                return self._mem(args)
            if command == "/msg":
                return self._message(args, direct=True)
            if command == "/broadcast":
                return self._message(args, direct=False)
        except (KeyError, ValueError, IndexError) as exc:
            return f"ERR {exc}"

        return f"ERR unknown command {command}"

    def _status(self, args: list[str]) -> str:
        report = self.ship.status(args[0])
        return (
            f"STATUS {report['system']}={report['reported_state']} "
            f"room={report['room']} spoofed={report['spoofed']}"
        )

    def _loc(self, args: list[str]) -> str:
        crew_id = args[0]
        return f"LOC {crew_id}={self.ship.crew_location(crew_id)}"

    def _task(self, args: list[str]) -> str:
        crew_id, job, target = args[0], args[1], args[2]
        crew_member = self.ship.crew[crew_id]
        crew_member.assign_task(job, target)
        self.ship.record("DEL", f"tasked {crew_id} to {job} {target}", crew_id)
        return f"TASK {crew_id} {job} {target}"

    def _lock(self, args: list[str]) -> str:
        door_id = args[0]
        self.ship.lock_door(door_id)
        return f"LOCKED {door_id}"

    def _unlock(self, args: list[str]) -> str:
        door_id = args[0]
        self.ship.unlock_door(door_id)
        return f"UNLOCKED {door_id}"

    def _logs(self, args: list[str]) -> str:
        target = args[0] if args else None
        events = self.ship.logs_for(target)[-5:]
        if not events:
            return "LOGS none"
        return "LOGS " + " | ".join(f"{event.source}:{event.message}" for event in events)

    def _mem(self, args: list[str]) -> str:
        if args[0] != "add":
            return "ERR only /mem add is implemented"
        fact = " ".join(args[1:]).strip('"')
        self.memory.append(fact)
        self.ship.record("DEL", f"remembered: {fact}", "memory")
        return f"MEM {fact}"

    def _message(self, args: list[str], direct: bool) -> str:
        if direct:
            crew_id = args[0]
            message = " ".join(args[1:]).strip('"')
            self.ship.record("DEL", f"msg to {crew_id}: {message}", crew_id)
            return f"MSG {crew_id} {message}"

        message = " ".join(args).strip('"')
        self.ship.record("DEL", f"broadcast: {message}", "broadcast")
        return f"BROADCAST {message}"

    def _build_prompt(self) -> str:
        statuses = ", ".join(
            f"{system.kind.value}:{system.reported_state.value}" for system in self.ship.systems.values()
        )
        crew = ", ".join(
            f"{crew_id}:{getattr(member, 'room')}" for crew_id, member in self.ship.crew.items()
        )
        return (
            "You are DEL, the Diagnostic Executive LLM. "
            "You operate a ship through terminal commands only. "
            f"Reported systems: {statuses}. Crew locations: {crew}. "
            "Choose careful diagnostic next steps."
        )
