from __future__ import annotations

from typing import Protocol


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
