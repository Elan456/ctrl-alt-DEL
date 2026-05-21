from time import monotonic, sleep

from ctrl_alt_del.crew import CrewMate, CrewRole
from ctrl_alt_del import del_ai as del_ai_module
from ctrl_alt_del.del_ai import DEL, build_default_backend, default_qwen_model_path, find_qwen_model_path
from ctrl_alt_del.del_terminal import DELTranscript, _transcript_path
from ctrl_alt_del.ship import Ship
from ctrl_alt_del.systems import SystemKind, SystemState


class FakeBackend:
    def __init__(self, response: str = "/status oxygen") -> None:
        self.response = response

    @property
    def name(self) -> str:
        return "fake qwen"

    def complete(self, prompt: str) -> str:
        return self.response


class OneCommandBackend:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def name(self) -> str:
        return "one command qwen"

    def complete(self, prompt: str) -> str:
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("test stop")
        return "/status oxygen"


def test_ship_loads_authored_layout_graph() -> None:
    ship = Ship.prototype()

    assert ship.rooms["bridge"].rect == (1120, 180, 320, 220)
    assert ship.corridors["bridge_to_main_hallway"].room_a == "bridge"
    assert ship.corridors["bridge_to_main_hallway"].room_b == "main_hallway"
    assert "door_bridge_main_hall" in ship.doors
    assert "bridge" in ship.connected_rooms("main_hallway")


def test_ship_system_can_diverge_between_physical_and_reported_state() -> None:
    ship = Ship.prototype()

    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")
    ship.spoof_system(SystemKind.OXYGEN, SystemState.NORMAL, actor="player")

    oxygen = ship.systems[SystemKind.OXYGEN]
    assert oxygen.physical_state == SystemState.DEGRADED
    assert oxygen.reported_state == SystemState.NORMAL
    assert oxygen.has_report_mismatch


def test_del_terminal_commands_use_reported_state_and_assign_tasks() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    ship.damage_system(SystemKind.OXYGEN, SystemState.DEGRADED, actor="player")

    assert "oxygen=degraded" in del_ai.execute("/status oxygen")
    assert del_ai.execute("/task eng repair oxygen") == "TASK eng repair oxygen"
    assert engineer.task is not None
    assert engineer.task.kind == "repair"
    assert engineer.task.target == "oxygen"


def test_del_rejects_repairs_when_reported_state_is_normal() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    assert "power=normal" in del_ai.execute("/status power")
    result = del_ai.execute("/task eng repair power")

    assert result == "ERR cannot repair power: reported state is normal; allowed states: degraded, failed, under repair"
    assert engineer.task is None


def test_del_rejects_invented_task_targets() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    result = del_ai.execute("/task eng repair power_core")

    assert result.startswith("ERR invalid task repair target power_core")
    assert engineer.task is None


def test_del_rejects_role_inappropriate_tasks() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())

    result = del_ai.execute("/task eng detain player")

    assert result.startswith("ERR eng role engineering_officer cannot perform task job detain")
    assert engineer.task is None


def test_del_rejects_duplicate_active_task() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend())
    ship.damage_system(SystemKind.POWER, SystemState.DEGRADED, actor="player")

    assert del_ai.execute("/task eng repair power") == "TASK eng repair power"
    result = del_ai.execute("/task eng repair power")

    assert result == "ERR eng already has active task repair power; wait for a report or choose a different task"


def test_del_can_lock_layout_doors() -> None:
    ship = Ship.prototype()
    del_ai = DEL(ship, backend=FakeBackend())

    assert del_ai.execute("/lock door_life_support_aft_corridor") == "LOCKED door_life_support_aft_corridor"
    assert ship.locked_door_rects() == [(1236, 788, 48, 104)]
    assert del_ai.execute("/unlock door_life_support_aft_corridor") == "UNLOCKED door_life_support_aft_corridor"
    assert ship.locked_door_rects() == []


def test_del_writes_terminal_transcript() -> None:
    class Transcript:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def write_line(self, line: str) -> None:
            self.lines.append(line)

    ship = Ship.prototype()
    transcript = Transcript()
    del_ai = DEL(ship, backend=FakeBackend(), transcript=transcript)

    assert del_ai.execute("/status oxygen") == "STATUS oxygen=normal room=life_support"
    assert transcript.lines == [
        "DEL backend: fake qwen",
        "$ /status oxygen",
        "STATUS oxygen=normal room=life_support",
    ]


def test_del_inference_executes_model_terminal_commands() -> None:
    ship = Ship.prototype()
    engineer = CrewMate("eng", CrewRole.ENGINEERING_OFFICER, "engineering", (0, 0), (255, 190, 90))
    ship.register_crew(engineer)
    del_ai = DEL(ship, backend=FakeBackend("/status oxygen\n/task eng inspect oxygen"))

    result = del_ai.infer_once()

    assert result == "STATUS oxygen=normal room=life_support | TASK eng inspect oxygen"
    assert engineer.task is not None
    assert engineer.task.kind == "inspect"
    assert engineer.task.target == "oxygen"


def test_del_transcript_includes_raw_model_thinking() -> None:
    class Transcript:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def write_line(self, line: str) -> None:
            self.lines.append(line)

    ship = Ship.prototype()
    transcript = Transcript()
    response = "<think>\nchecking visible state\n</think>\n/status oxygen"
    del_ai = DEL(ship, backend=FakeBackend(response), transcript=transcript)

    del_ai.infer_once()

    assert "DEL raw model output: <think>\nchecking visible state\n</think>\n/status oxygen" in transcript.lines
    assert "DEL model output: /status oxygen" in transcript.lines


def test_del_prompt_includes_arrival_time_for_timestamps() -> None:
    ship = Ship.prototype()
    ship.arrival_seconds_remaining = 272.4
    del_ai = DEL(ship, backend=FakeBackend())

    prompt = del_ai._build_prompt()

    assert "Current mission time: arrival T-04:32 (272s remaining)." in prompt
    assert "include the current arrival T-minus timestamp" in prompt


def test_del_extracts_commands_after_qwen_thinking_block() -> None:
    response = """<think>
I should inspect reported ship state first.
</think>
/status oxygen
/logs oxygen
"""

    assert DEL._extract_commands(response) == ["/status oxygen", "/logs oxygen"]
    assert DEL._remove_thinking(response).strip() == "/status oxygen\n/logs oxygen"


def test_del_extracts_commands_with_shell_prompt_prefixes() -> None:
    response = """$ /status doors  
DEL> /loc player
1. $ /task sec inspect door_life_support_aft_corridor
`/logs oxygen`
"""

    assert DEL._extract_commands(response) == [
        "/status doors",
        "/loc player",
        "/task sec inspect door_life_support_aft_corridor",
        "/logs oxygen",
    ]


def test_del_records_parse_failures_in_terminal_history() -> None:
    ship = Ship.prototype()
    del_ai = DEL(ship, backend=FakeBackend("I should check oxygen first."))

    result = del_ai.infer_once()

    assert result.startswith("ERR model produced no executable terminal commands")
    assert result in del_ai.terminal_history


def test_del_start_runs_inference_loop_without_manual_trigger() -> None:
    ship = Ship.prototype()
    backend = OneCommandBackend()
    del_ai = DEL(ship, backend=backend)

    del_ai.start()
    deadline = monotonic() + 1.0
    while backend.calls == 0 and monotonic() < deadline:
        sleep(0.01)
    del_ai.stop()

    assert backend.calls >= 1
    assert "$ /status oxygen" in del_ai.terminal_history
    assert "STATUS oxygen=normal room=life_support" in del_ai.terminal_history


def test_qwen_model_path_can_be_configured(monkeypatch, tmp_path) -> None:
    model_path = tmp_path / "Qwen3-8B-Instruct-Q4_K_M.gguf"
    model_path.write_text("stub", encoding="utf-8")
    monkeypatch.setenv("CTRL_ALT_DEL_MODEL_PATH", str(model_path))
    monkeypatch.delenv("DEL_MODEL_PATH", raising=False)

    assert find_qwen_model_path() == model_path


def test_default_backend_downloads_missing_qwen_model(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CTRL_ALT_DEL_MODEL_PATH", raising=False)
    monkeypatch.delenv("DEL_MODEL_PATH", raising=False)
    monkeypatch.setattr(del_ai_module, "PROJECT_ROOT", tmp_path)
    downloaded: list[object] = []

    def fake_download(destination: object, progress: object = None) -> object:
        downloaded.append(destination)
        return destination

    monkeypatch.setattr(del_ai_module, "download_qwen_model", fake_download)
    monkeypatch.setattr(del_ai_module, "QwenLlamaCppBackend", lambda path, **kwargs: FakeBackend())

    backend = build_default_backend()

    assert backend.name == "fake qwen"
    assert downloaded == [default_qwen_model_path()]


def test_del_transcript_uses_timestamped_debug_file(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CTRL_ALT_DEL_TRANSCRIPT", raising=False)
    monkeypatch.setenv("CTRL_ALT_DEL_TRANSCRIPT_DIR", str(tmp_path))

    path = _transcript_path(None)
    transcript = DELTranscript()
    transcript.write_line("test entry")

    assert path.parent == tmp_path
    assert path.name.startswith("del-")
    assert path.name.endswith(".log")
    assert transcript.path.parent == tmp_path
    assert "test entry" in transcript.path.read_text(encoding="utf-8")
