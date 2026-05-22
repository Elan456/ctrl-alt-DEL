from __future__ import annotations

from ctrl_alt_del.del_ai import DELTranscript, spawn_del_terminal
from ctrl_alt_del.game import Game


def main() -> int:
    transcript = DELTranscript()
    terminal = spawn_del_terminal(transcript.path)
    if terminal is None:
        print(f"DEL transcript: {transcript.path}")
    try:
        return Game(del_transcript=transcript).run()
    except Exception as exc:
        transcript.write_line(f"DEL startup error: {exc}")
        raise
