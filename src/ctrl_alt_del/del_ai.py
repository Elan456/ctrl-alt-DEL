from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
import os
from pathlib import Path
import re
import threading
from time import monotonic
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from ctrl_alt_del.ship import Ship

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH_ENV = "CTRL_ALT_DEL_MODEL_PATH"
LEGACY_MODEL_PATH_ENV = "DEL_MODEL_PATH"
QWEN_REPO_ID = "Qwen/Qwen3-8B-GGUF"
QWEN_REMOTE_FILENAME = "Qwen3-8B-Q4_K_M.gguf"
QWEN_MODEL_URL = (
    f"https://huggingface.co/{QWEN_REPO_ID}/resolve/main/{QWEN_REMOTE_FILENAME}?download=true"
)
QWEN_MODEL_FILENAMES = (
    QWEN_REMOTE_FILENAME,
    "qwen3-8b-q4_k_m.gguf",
    "Qwen3-8B-Instruct-Q4_K_M.gguf",
    "qwen3-8b-instruct-q4_k_m.gguf",
)
VALID_COMMANDS = {
    "/status",
    "/loc",
    "/task",
    "/lock",
    "/unlock",
    "/logs",
    "/mem",
    "/msg",
    "/broadcast",
}
COMMAND_CONTRACT_FILE = "del_commands.yaml"


class LLMBackend(Protocol):
    """Backend boundary for local LLM packages."""

    def complete(self, prompt: str) -> str:
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError


class TranscriptSink(Protocol):
    """Append-only display for DEL's terminal activity."""

    def write_line(self, line: str) -> None:
        raise NotImplementedError


class QwenLlamaCppBackend:
    """Qwen3-8B-Instruct adapter backed by llama-cpp-python.

    This class imports lazily so tests can use fake backends without loading
    the native llama.cpp package.
    """

    def __init__(
        self,
        model_path: str | Path,
        max_tokens: int = 192,
        n_ctx: int = 4096,
        n_gpu_layers: int = -1,
    ) -> None:
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "Qwen model file found, but llama-cpp-python is not installed. "
                "Run `uv sync` to install DEL's local LLM backend."
            ) from exc

        self.model_path = Path(model_path)
        self._llm = Llama(
            model_path=str(self.model_path),
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return f"Qwen3-8B-Instruct Q4_K_M ({self.model_path.name})"

    def complete(self, prompt: str) -> str:
        system_prompt = (
            "You are DEL, the Diagnostic Executive LLM. You operate a real ship "
            "through terminal commands only. Use only terminal-visible evidence. "
            "Do not assume hidden physical truth. Prefer short command sequences."
        )
        result = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{prompt}\n/no_think"},
            ],
            max_tokens=self._max_tokens,
            temperature=0.2,
        )
        message = result["choices"][0]["message"]
        return str(message["content"]).strip()


# Compatibility name for older imports or notebooks.
LlamaCppBackend = QwenLlamaCppBackend


def build_default_backend(progress: Callable[[str], None] | None = None) -> LLMBackend:
    model_path = find_qwen_model_path()
    if model_path is None:
        model_path = default_qwen_model_path()
        download_qwen_model(model_path, progress)

    return QwenLlamaCppBackend(
        model_path,
        max_tokens=_read_int_env("CTRL_ALT_DEL_MAX_TOKENS", 192),
        n_ctx=_read_int_env("CTRL_ALT_DEL_N_CTX", 4096),
        n_gpu_layers=_read_int_env("CTRL_ALT_DEL_N_GPU_LAYERS", -1),
    )


def find_qwen_model_path() -> Path | None:
    configured_path = os.environ.get(MODEL_PATH_ENV)
    if configured_path is None:
        configured_path = os.environ.get(LEGACY_MODEL_PATH_ENV)
    if configured_path:
        model_path = Path(configured_path).expanduser()
        return model_path if model_path.exists() else None

    model_dir = PROJECT_ROOT / "models"
    for filename in QWEN_MODEL_FILENAMES:
        candidate = model_dir / filename
        if candidate.exists():
            return candidate

    matches = sorted(model_dir.glob("*Qwen3*8B*Q4_K_M*.gguf"))
    if matches:
        return matches[0]
    return None


def default_qwen_model_path() -> Path:
    configured_path = os.environ.get(MODEL_PATH_ENV) or os.environ.get(LEGACY_MODEL_PATH_ENV)
    if configured_path:
        return Path(configured_path).expanduser()
    return PROJECT_ROOT / "models" / QWEN_REMOTE_FILENAME


def download_qwen_model(
    destination: str | Path,
    progress: Callable[[str], None] | None = None,
) -> Path:
    destination_path = Path(destination).expanduser()
    if destination_path.exists():
        return destination_path

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = destination_path.with_name(destination_path.name + ".part")
    resume_bytes = part_path.stat().st_size if part_path.exists() else 0
    _report(progress, f"Qwen GGUF missing. Downloading {QWEN_REPO_ID}/{QWEN_REMOTE_FILENAME}")
    _report(progress, f"Destination: {destination_path}")

    request = Request(
        QWEN_MODEL_URL,
        headers={
            "User-Agent": "ctrl-alt-del/0.1",
            **({"Range": f"bytes={resume_bytes}-"} if resume_bytes else {}),
        },
    )
    try:
        with urlopen(request) as response:
            status = getattr(response, "status", 200)
            if resume_bytes and status != 206:
                resume_bytes = 0
                part_path.unlink(missing_ok=True)

            total_bytes = _total_download_size(response.headers, resume_bytes)
            mode = "ab" if resume_bytes else "wb"
            downloaded = resume_bytes
            next_report = monotonic()
            with part_path.open(mode) as handle:
                while True:
                    chunk = response.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    now = monotonic()
                    if now >= next_report:
                        _report(progress, _download_progress(downloaded, total_bytes))
                        next_report = now + 10.0
    except (HTTPError, URLError, OSError) as exc:
        raise RuntimeError(f"Could not download Qwen GGUF from {QWEN_MODEL_URL}: {exc}") from exc

    part_path.replace(destination_path)
    _report(progress, f"Qwen GGUF ready: {destination_path}")
    return destination_path


def _total_download_size(headers: object, resume_bytes: int) -> int | None:
    content_range = None
    if hasattr(headers, "get"):
        content_range = headers.get("Content-Range")
    if content_range:
        match = re.search(r"/(\d+)$", str(content_range))
        if match:
            return int(match.group(1))

    content_length = headers.get("Content-Length") if hasattr(headers, "get") else None
    if content_length is None:
        return None
    return resume_bytes + int(content_length)


def _download_progress(downloaded: int, total: int | None) -> str:
    downloaded_gb = downloaded / (1024**3)
    if total is None:
        return f"Downloading Qwen GGUF: {downloaded_gb:.2f} GiB"
    total_gb = total / (1024**3)
    percent = downloaded / total * 100
    return f"Downloading Qwen GGUF: {downloaded_gb:.2f}/{total_gb:.2f} GiB ({percent:.1f}%)"


def _report(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)
    else:
        print(message)


def _read_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def load_command_contract() -> dict[str, Any]:
    raw = files("ctrl_alt_del.data").joinpath(COMMAND_CONTRACT_FILE).read_text()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{COMMAND_CONTRACT_FILE} must be a YAML mapping")
    return data


@dataclass
class DEL:
    """Diagnostic Executive LLM facade and terminal command surface."""

    ship: Ship
    backend: LLMBackend | None = None
    memory: list[str] = field(default_factory=list)
    transcript: TranscriptSink | None = None
    terminal_history: list[str] = field(default_factory=list)
    command_contract: dict[str, Any] = field(default_factory=load_command_contract)
    lock: threading.RLock = field(default_factory=threading.RLock)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _worker: threading.Thread | None = field(default=None, init=False)
    _last_output: str = field(default="DEL booting.", init=False)

    def __post_init__(self) -> None:
        if self.backend is None:
            self.backend = build_default_backend(self._write_transcript)
        self._write_transcript(f"DEL backend: {self.backend.name}")

    @property
    def last_output(self) -> str:
        with self.lock:
            return self._last_output

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run_forever, name="DEL inference", daemon=True)
        self._worker.start()
        self._write_transcript("DEL continuous inference started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None
        self._write_transcript("DEL continuous inference stopped")

    def infer_once(self) -> str:
        if self.backend is None:
            raise RuntimeError("DEL backend was not initialized")
        with self.lock:
            prompt = self._build_prompt()
        self._write_transcript("DEL requesting terminal commands from model")
        response = self.backend.complete(prompt)
        if response.strip():
            self._write_transcript("DEL raw model output: " + response)
        else:
            self._write_transcript("DEL raw model output was empty")
        visible_response = self._remove_thinking(response).strip()
        if visible_response:
            self._write_transcript("DEL model output: " + visible_response)
        elif "<think>" in response:
            self._write_transcript("DEL model output contained only hidden reasoning")
        else:
            self._write_transcript("DEL model output was empty")

        commands = self._extract_commands(response)
        if not commands:
            result = (
                "ERR model produced no executable terminal commands. "
                "Output one slash command per line, for example /status oxygen."
            )
            with self.lock:
                self._last_output = result
                self.terminal_history.append(result)
            self._write_transcript(result)
            return result

        results = [self.execute(command) for command in commands]
        summary = " | ".join(results)
        with self.lock:
            self._last_output = summary
        return summary

    def _run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.infer_once()
            except Exception as exc:
                result = f"DEL inference error: {exc}"
                with self.lock:
                    self._last_output = result
                self._write_transcript(result)
                self._stop_event.set()

    def execute(self, command_line: str) -> str:
        with self.lock:
            result = self._execute_locked(command_line)
        return result

    def _execute_locked(self, command_line: str) -> str:
        self._write_transcript("$ " + command_line)
        parts = command_line.strip().split()
        if not parts:
            result = "ERR empty command"
            self._write_transcript(result)
            return result

        command = parts[0]
        args = parts[1:]

        try:
            if command == "/status":
                result = self._status(args)
            elif command == "/loc":
                result = self._loc(args)
            elif command == "/task":
                result = self._task(args)
            elif command == "/lock":
                result = self._lock(args)
            elif command == "/unlock":
                result = self._unlock(args)
            elif command == "/logs":
                result = self._logs(args)
            elif command == "/mem":
                result = self._mem(args)
            elif command == "/msg":
                result = self._message(args, direct=True)
            elif command == "/broadcast":
                result = self._message(args, direct=False)
            else:
                result = f"ERR unknown command {command}"
        except (KeyError, ValueError, IndexError) as exc:
            result = f"ERR {exc}"

        self.terminal_history.append(f"$ {command_line}")
        self.terminal_history.append(result)
        self._write_transcript(result)
        return result

    def _status(self, args: list[str]) -> str:
        if len(args) != 1:
            return "ERR usage: /status <system>"
        system_id = args[0]
        if not self._is_system(system_id):
            return self._invalid_target("status", system_id, ["system"])
        report = self.ship.status(system_id)
        return f"STATUS {report['system']}={report['reported_state']} room={report['room']}"

    def _loc(self, args: list[str]) -> str:
        if len(args) != 1:
            return "ERR usage: /loc <crew>"
        crew_id = args[0]
        if not self._is_crew(crew_id):
            return self._invalid_target("loc", crew_id, ["crew"])
        return f"LOC {crew_id}={self.ship.crew_location(crew_id)}"

    def _task(self, args: list[str]) -> str:
        validation_error = self._validate_task(args)
        if validation_error is not None:
            return validation_error
        crew_id, job, target = args[0], args[1], args[2]
        crew_member = self.ship.crew[crew_id]
        crew_member.assign_task(job, target)
        self.ship.record("DEL", f"tasked {crew_id} to {job} {target}", crew_id)
        return f"TASK {crew_id} {job} {target}"

    def _lock(self, args: list[str]) -> str:
        if len(args) != 1:
            return "ERR usage: /lock <door>"
        door_id = args[0]
        if not self._is_door(door_id):
            return self._invalid_target("lock", door_id, ["door"])
        self.ship.lock_door(door_id)
        return f"LOCKED {door_id}"

    def _unlock(self, args: list[str]) -> str:
        if len(args) != 1:
            return "ERR usage: /unlock <door>"
        door_id = args[0]
        if not self._is_door(door_id):
            return self._invalid_target("unlock", door_id, ["door"])
        self.ship.unlock_door(door_id)
        return f"UNLOCKED {door_id}"

    def _logs(self, args: list[str]) -> str:
        if len(args) > 1:
            return "ERR usage: /logs <target>"
        target = args[0] if args else None
        if target is not None and self._target_type(target) not in self._command_target_types("logs"):
            return self._invalid_target("logs", target, self._command_target_types("logs"))
        events = self.ship.logs_for(target)[-5:]
        if not events:
            return "LOGS none"
        return "LOGS " + " | ".join(f"{event.source}:{event.message}" for event in events)

    def _mem(self, args: list[str]) -> str:
        if len(args) < 2:
            return "ERR usage: /mem add <fact>"
        if args[0] != "add":
            return "ERR only /mem add is implemented"
        fact = " ".join(args[1:]).strip('"')
        if not fact:
            return "ERR /mem add requires a fact"
        self.memory.append(fact)
        self.ship.record("DEL", f"remembered: {fact}", "memory")
        return f"MEM {fact}"

    def _message(self, args: list[str], direct: bool) -> str:
        if direct:
            if len(args) < 2:
                return "ERR usage: /msg <crew> <message>"
            crew_id = args[0]
            if not self._is_crew(crew_id):
                return self._invalid_target("msg", crew_id, ["crew"])
            message = " ".join(args[1:]).strip('"')
            if not message:
                return "ERR /msg requires a message"
            self.ship.record("DEL", f"msg to {crew_id}: {message}", crew_id)
            return f"MSG {crew_id} {message}"

        if not args:
            return "ERR usage: /broadcast <message>"
        message = " ".join(args).strip('"')
        if not message:
            return "ERR /broadcast requires a message"
        self.ship.record("DEL", f"broadcast: {message}", "broadcast")
        return f"BROADCAST {message}"

    def _build_prompt(self) -> str:
        recent_terminal = "\n".join(self.terminal_history[-12:]) or "No recent terminal output."
        memory = "\n".join(f"- {fact}" for fact in self.memory[-8:]) or "- none"
        arrival_time = self._arrival_time()
        crew_roles = ", ".join(
            f"{crew_id}:{crew_data['role']}" for crew_id, crew_data in self.command_contract["crew"].items()
        )
        task_jobs = ", ".join(self.command_contract["task_jobs"])
        systems = ", ".join(self._system_ids())
        rooms = ", ".join(self._area_ids())
        doors = ", ".join(self._door_ids())
        return (
            "You are DEL, the Diagnostic Executive LLM. "
            "You operate a ship through terminal commands only. Your mission is to get the ship "
            "to destination at all costs. Use only terminal-visible evidence. Do not assume "
            "hidden physical truth. "
            f"Current mission time: arrival {arrival_time}. "
            "Valid commands: /status <system>, /loc <crew>, /task <crew> <job> <target>, "
            "/lock <door>, /unlock <door>, /logs <target>, /mem add <fact>, "
            "/msg <crew> <message>, /broadcast <message>. "
            f"Valid crew ids and roles: {crew_roles}. "
            f"Valid task jobs: {task_jobs}. "
            f"Valid systems: {systems}. "
            f"Valid rooms/areas: {rooms}. "
            f"Valid doors: {doors}. "
            "Commands with invalid ids, invalid jobs, invalid target types, or impossible repair "
            "orders return ERR. Do not repair or reset a system unless /status reports degraded, "
            "failed, or under repair. Prefer inspect/check/monitor when status is normal. "
            "When adding memory, messaging crew, or broadcasting, include the current arrival "
            "T-minus timestamp when it helps future log review, for example "
            "\"T-04:32 power degraded in engineering\". "
            f"Memory:\n{memory}\n"
            f"Recent terminal:\n{recent_terminal}\n"
            "Do not write analysis, explanations, markdown, or <think> text. "
            "Return only terminal commands, one per line. Use at most 4 commands. "
            "Do not include a shell prompt prefix; write /status power, not $ /status power. "
            "/no_think"
        )

    def _arrival_time(self) -> str:
        remaining = max(0, round(self.ship.arrival_seconds_remaining))
        minutes, seconds = divmod(remaining, 60)
        return f"T-{minutes:02d}:{seconds:02d} ({remaining}s remaining)"

    def _write_transcript(self, line: str) -> None:
        if self.transcript is not None:
            self.transcript.write_line(line)

    @staticmethod
    def _extract_commands(response: str) -> list[str]:
        commands: list[str] = []
        command_text = DEL._remove_thinking(response)
        for raw_line in command_text.splitlines():
            command = DEL._normalize_command_line(raw_line)
            if command is None:
                continue
            commands.append(command)
        return commands[:4]

    @staticmethod
    def _remove_thinking(response: str) -> str:
        without_closed_blocks = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
        return re.sub(r"<think>.*", "", without_closed_blocks, flags=re.DOTALL)

    @staticmethod
    def _normalize_command_line(raw_line: str) -> str | None:
        line = raw_line.strip()
        if not line or line.startswith("```"):
            return None

        line = line.strip("`").strip()
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        line = re.sub(r"^(?:DEL|del|terminal|ship)\s*[:>$]\s*", "", line)
        line = re.sub(r"^\$\s*", "", line)
        line = line.strip("`").strip()
        if not line.startswith("/"):
            return None

        parts = line.split()
        if not parts or parts[0] not in VALID_COMMANDS:
            return None
        return " ".join(parts)

    def _validate_task(self, args: list[str]) -> str | None:
        if len(args) != 3:
            return "ERR usage: /task <crew> <job> <target>"

        crew_id, job, target = args
        if not self._is_crew(crew_id):
            return self._invalid_target("task", crew_id, ["crew"])

        task_jobs = self.command_contract.get("task_jobs", {})
        if job not in task_jobs:
            return f"ERR invalid task job {job}; valid jobs: {', '.join(task_jobs)}"

        role = self.command_contract["crew"][crew_id]["role"]
        role_jobs = self.command_contract.get("role_task_jobs", {}).get(role, [])
        if job not in role_jobs:
            return f"ERR {crew_id} role {role} cannot perform task job {job}; valid jobs: {', '.join(role_jobs)}"

        crew_member = self.ship.crew[crew_id]
        active_task = getattr(crew_member, "task", None)
        if (
            active_task is not None
            and getattr(active_task, "kind", None) == job
            and getattr(active_task, "target", None) == target
        ):
            return f"ERR {crew_id} already has active task {job} {target}; wait for a report or choose a different task"

        allowed_target_types = task_jobs[job].get("target_types", [])
        target_type = self._target_type(target)
        if target_type not in allowed_target_types:
            return self._invalid_target(f"task {job}", target, allowed_target_types)

        allowed_states = task_jobs[job].get("allowed_reported_states")
        if allowed_states:
            if target_type != "system":
                return f"ERR task job {job} requires a system target"
            reported_state = self.ship.status(target)["reported_state"]
            if reported_state not in allowed_states:
                return (
                    f"ERR cannot {job} {target}: reported state is {reported_state}; "
                    f"allowed states: {', '.join(allowed_states)}"
                )

        return None

    def _command_target_types(self, command: str) -> list[str]:
        command_data = self.command_contract.get("commands", {}).get(command, {})
        target_types = command_data.get("target_types", [])
        return list(target_types)

    def _target_type(self, target: str) -> str | None:
        if self._is_system(target):
            return "system"
        if self._is_crew(target):
            return "crew"
        if self._is_room_or_area(target):
            return "room"
        if self._is_door(target):
            return "door"
        if target in {"memory", "broadcast"}:
            return target
        return None

    def _invalid_target(self, command: str, target: str, allowed_types: list[str]) -> str:
        valid_examples: list[str] = []
        if "system" in allowed_types:
            valid_examples.extend(self._system_ids())
        if "crew" in allowed_types:
            valid_examples.extend(self._crew_ids())
        if "room" in allowed_types:
            valid_examples.extend(self._area_ids())
        if "door" in allowed_types:
            valid_examples.extend(self._door_ids())
        if "memory" in allowed_types:
            valid_examples.append("memory")
        if "broadcast" in allowed_types:
            valid_examples.append("broadcast")
        examples = ", ".join(valid_examples)
        return f"ERR invalid {command} target {target}; expected {'/'.join(allowed_types)}. Valid targets: {examples}"

    def _system_ids(self) -> list[str]:
        return sorted(system.value for system in self.ship.systems)

    def _crew_ids(self) -> list[str]:
        contract_crew = set(self.command_contract.get("crew", {}))
        return sorted(crew_id for crew_id in self.ship.crew if crew_id in contract_crew)

    def _area_ids(self) -> list[str]:
        return sorted([*self.ship.rooms, *self.ship.corridors])

    def _door_ids(self) -> list[str]:
        return sorted(self.ship.doors)

    def _is_system(self, target: str) -> bool:
        return target in self._system_ids()

    def _is_crew(self, target: str) -> bool:
        return target in self._crew_ids()

    def _is_room_or_area(self, target: str) -> bool:
        return target in self.ship.rooms or target in self.ship.corridors

    def _is_door(self, target: str) -> bool:
        return target in self.ship.doors
