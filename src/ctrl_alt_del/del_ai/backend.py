from __future__ import annotations

import os
from pathlib import Path
import re
from time import monotonic
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ctrl_alt_del.del_ai.protocols import LLMBackend

PROJECT_ROOT = Path(__file__).resolve().parents[3]
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


class QwenLlamaCppBackend:
    """Qwen3-8B-Instruct adapter backed by llama-cpp-python."""

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
            "through validated structured terminal actions only. Use only terminal-visible evidence. "
            "Do not assume hidden physical truth. Return only the requested structured output."
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
