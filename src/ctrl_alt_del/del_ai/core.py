from __future__ import annotations

from dataclasses import dataclass, field
import threading
from time import monotonic
from typing import Any

from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from ctrl_alt_del.del_ai.actions import DEL_ACTION_INSTRUCTIONS, DELActionPlan
from ctrl_alt_del.del_ai.backend import build_default_backend
from ctrl_alt_del.del_ai.commands import ActionExecutorMixin
from ctrl_alt_del.del_ai.contract import load_command_contract
from ctrl_alt_del.del_ai.prompting import arrival_time, build_prompt
from ctrl_alt_del.del_ai.protocols import LLMBackend, TranscriptSink
from ctrl_alt_del.ship import Ship


@dataclass
class DEL(ActionExecutorMixin):
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
        self._write_transcript("DEL requesting structured action plan from model")
        self._write_transcript("DEL action prompt:\n" + prompt)
        raw_outputs: list[str] = []
        try:
            action_plan = self._generate_action_plan(prompt, raw_outputs)
        except Exception as exc:
            self._write_raw_model_outputs(raw_outputs)
            result = f"ERR model produced invalid structured action plan: {exc}"
            with self.lock:
                self._last_output = result
                self._append_terminal_history(result)
            self._write_transcript(result)
            return result

        self._write_raw_model_outputs(raw_outputs)
        action_count = len(action_plan.actions)
        action_label = "DEL structured action" if action_count == 1 else "DEL structured actions"
        self._write_transcript(
            f"{action_label}: "
            + " | ".join(action.model_dump_json() for action in action_plan.actions)
        )
        summary = self.execute_actions(action_plan.actions)
        with self.lock:
            self._last_output = summary
        return summary

    def _generate_action_plan(self, prompt: str, raw_outputs: list[str]) -> DELActionPlan:
        def model_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            model_prompt = self._format_pydantic_ai_request(messages, info)
            if not model_prompt.strip():
                model_prompt = prompt
            self._write_transcript("DEL raw LLM prompt:\n" + model_prompt)
            self._write_transcript("DEL raw LLM request started")
            started_at = monotonic()
            raw_output = self.backend.complete(model_prompt) if self.backend is not None else ""
            elapsed = monotonic() - started_at
            self._write_transcript(f"DEL raw LLM request completed in {elapsed:.2f}s")
            raw_outputs.append(raw_output)
            return ModelResponse(parts=[TextPart(self._remove_thinking(raw_output).strip())])

        agent = Agent(
            FunctionModel(model_function, model_name=self.backend.name if self.backend is not None else "del-backend"),
            output_type=PromptedOutput(DELActionPlan),
            instructions=DEL_ACTION_INSTRUCTIONS,
            retries=1,
        )
        result = agent.run_sync(prompt)
        return result.output

    @staticmethod
    def _format_pydantic_ai_request(messages: list[ModelMessage], info: AgentInfo) -> str:
        sections: list[str] = []
        if info.instructions:
            sections.append(str(info.instructions))

        for message in messages:
            for part in getattr(message, "parts", []):
                content = getattr(part, "content", None)
                if content is None:
                    continue
                if isinstance(content, list):
                    content = "\n".join(str(item) for item in content)
                sections.append(str(content))

        return "\n\n".join(section for section in sections if section.strip())

    def _write_raw_model_outputs(self, raw_outputs: list[str]) -> None:
        if not raw_outputs:
            self._write_transcript("DEL raw model output was empty")
            return

        for index, response in enumerate(raw_outputs, start=1):
            label = "DEL raw model output" if len(raw_outputs) == 1 else f"DEL raw model output attempt {index}"
            if response.strip():
                self._write_transcript(label + ": " + response)
            else:
                self._write_transcript(label + " was empty")

            visible_response = self._remove_thinking(response).strip()
            visible_label = "DEL model output" if len(raw_outputs) == 1 else f"DEL model output attempt {index}"
            if visible_response:
                self._write_transcript(visible_label + ": " + visible_response)
            elif "<think>" in response:
                self._write_transcript(visible_label + " contained only hidden reasoning")
            else:
                self._write_transcript(visible_label + " was empty")

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

    def _build_prompt(self) -> str:
        return build_prompt(self)

    def _arrival_time(self) -> str:
        return arrival_time(self.ship.arrival_seconds_remaining)

    def _append_terminal_history(self, line: str) -> None:
        self.terminal_history.append(f"[{self._arrival_time()}] {line}")

    def _write_transcript(self, line: str) -> None:
        print(line.rstrip(), flush=True)
        if self.transcript is not None:
            self.transcript.write_line(line)
