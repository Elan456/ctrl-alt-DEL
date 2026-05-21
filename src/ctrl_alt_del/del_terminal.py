from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shlex
import shutil
import subprocess

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSCRIPT_PATH_ENV = "CTRL_ALT_DEL_TRANSCRIPT"
TRANSCRIPT_DIR_ENV = "CTRL_ALT_DEL_TRANSCRIPT_DIR"
NO_TERMINAL_ENV = "CTRL_ALT_DEL_NO_TERMINAL"


class DELTranscript:
    """Append-only transcript for DEL's ship terminal activity."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = _transcript_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            f"DEL terminal transcript started {datetime.now().isoformat(timespec='seconds')}\n",
            encoding="utf-8",
        )

    def write_line(self, line: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line.rstrip() + "\n")


def spawn_del_terminal(transcript_path: str | Path) -> subprocess.Popen[bytes] | None:
    """Open a terminal emulator that follows the DEL transcript."""

    if os.environ.get(NO_TERMINAL_ENV):
        return None
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return None

    path = Path(transcript_path)
    quoted_path = shlex.quote(str(path))
    parent_pid = os.getpid()
    follow_command = (
        "printf 'DEL ship terminal transcript: %s\\n\\n' "
        f"{quoted_path}; "
        f"tail --pid={parent_pid} -n +1 -f {quoted_path} 2>/dev/null "
        f"|| tail -n +1 -f {quoted_path}"
    )

    command = _terminal_command(follow_command)
    if command is None:
        return None

    try:
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None


def _transcript_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path).expanduser()
    configured_path = os.environ.get(TRANSCRIPT_PATH_ENV)
    if configured_path:
        return Path(configured_path).expanduser()

    configured_dir = os.environ.get(TRANSCRIPT_DIR_ENV)
    transcript_dir = Path(configured_dir).expanduser() if configured_dir else PROJECT_ROOT / "debug" / "del-transcripts"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return transcript_dir / f"del-{timestamp}-{os.getpid()}.log"


def _terminal_command(follow_command: str) -> list[str] | None:
    candidates = (
        ("konsole", ["konsole", "--new-tab", "-p", "tabtitle=DEL Terminal", "-e"]),
        ("gnome-terminal", ["gnome-terminal", "--title=DEL Terminal", "--"]),
        ("xfce4-terminal", ["xfce4-terminal", "--title=DEL Terminal", "--command"]),
        ("xterm", ["xterm", "-T", "DEL Terminal", "-e"]),
        ("x-terminal-emulator", ["x-terminal-emulator", "-T", "DEL Terminal", "-e"]),
    )
    for executable, prefix in candidates:
        if shutil.which(executable) is None:
            continue
        if executable == "xfce4-terminal":
            return prefix + [f"sh -lc {shlex.quote(follow_command)}"]
        return prefix + ["sh", "-lc", follow_command]
    return None
