"""Shared fixtures: a real hub room with a HubClient-shaped urllib client."""

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from pot.board import Board
from pot.hub.app import Hub
from pot.protocol import Envelope, deserialize
from pot.roles import RoleRepo


class Client:
    """Raw urllib client for the loopback hub: (status_code, body_dict) answers.

    poll/poll_raw drive /api/poll — one of the session-family routes spec §10-3
    keeps alive after the room-protocol cut.
    """

    def __init__(self, base: str, token: str, host: str):
        self.base = base.rstrip("/")
        self.token = token
        self.host = host

    # ── raw HTTP ──

    def _json(self, method: str, path: str, obj: dict) -> tuple[int, dict]:
        data = json.dumps(obj).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def post(self, path: str, obj: dict) -> tuple[int, dict]:
        return self._json("POST", path, obj)

    def get(self, path: str) -> tuple[int, dict]:
        try:
            with urllib.request.urlopen(self.base + path, timeout=40) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def poll_raw(self, host: str, after: int = 0, timeout: float = 0.0) -> tuple[int, dict]:
        return self.get(f"/api/poll?host={host}&token={self.token}&after={after}&timeout={timeout}")

    def poll(self, after: int, timeout: float) -> tuple[list[Envelope], int]:
        _code, out = self.poll_raw(self.host, after, timeout)
        return [deserialize(m) for m in out["messages"]], out["cursor"]


@pytest.fixture()
def room(tmp_path):
    hub = Hub("srv", "room-token", tmp_path)
    hub.start()
    names = ("alpha", "beta", "srv")
    clients = {n: Client(f"http://127.0.0.1:{hub.port}", "room-token", n) for n in names}
    yield hub, clients
    hub.stop()


@pytest.fixture(autouse=True)
def _never_write_the_user_config(tmp_path, monkeypatch):
    """Point the one config path at a throwaway, always-present file.

    2026-09-10: the GUI tests patched `gui.load_config`/`gui.save_config`, which
    the split `pot/gui/` package no longer reads — so a "save the courier
    memory" test wrote its own string into the user's real long-term memory
    (and the settings test wrote its key). Per-test patching is one rename away
    from missing again: redirect the path itself, here, for every test.

    2026-09-23: seed the sandbox file, never the machine's real config.json.
    The old copy-if-present made the suite's inputs depend on the machine
    running it: a fresh clone has no config.json, so the sandbox file never
    appeared (FileNotFoundError in the quotes-refusal test on the v0.9.0
    Release runner). Every machine seeds the same bytes, so every machine runs
    the same suite.

    2026-09-30: seed a *configured* key (`api_key` set, never the default).
    `{}` left `/config-status` answering "unconfigured", so every page load
    raced the API-key overlay: each webui fixture removes `show` once after
    load, but app.js adds it back whenever its own `/config-status` fetch
    resolves *later* — the overlay then sat on top of the pane and Playwright's
    clicks timed out on `<div class="show" id="config-overlay">` (seen
    locally on test_webui_rate / test_webui_sessions, shuffled run to run).
    With a configured seed the overlay never appears, and the fixtures'
    remove('show') stays as belt to that braces. No test asserts the
    unconfigured state (checked: no /config-status, api_key==default, or
    overlay-showing assertions anywhere).
    """
    from pot import config as config_mod

    # A subdirectory, not tmp_path itself: tests that treat tmp_path as a data
    # directory (test_session's SESSIONS_DIR) glob it for *.json.
    target = tmp_path / "user-config" / "config.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"api_key": "k"}', encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_PATH", target)


class WebUIHost:
    """Loopback WebUI server for tests — the harness that replaced the cut
    RoomServer (spec §1.2). Sessions land in the given dir, never the repo's;
    `llm` (if given) becomes every agent's `_default_llm` (the SilentLLM shape:
    callable(messages, tool_defs) -> LLMResult)."""

    def __init__(self, server, runtime, mp):
        self.server = server
        self.runtime = runtime
        self._mp = mp
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()

    @classmethod
    def start(cls, session_dir=None, llm=None):
        from pot import session as session_mod
        from pot.agent import Agent
        from pot.server import WebUIRuntime, make_webui_server

        mp = pytest.MonkeyPatch()
        if session_dir is not None:
            Path(session_dir).mkdir(parents=True, exist_ok=True)
            mp.setattr(session_mod, "SESSIONS_DIR", Path(session_dir))
        if llm is not None:
            mp.setattr(Agent, "_default_llm", llm)
        # Any turn schedules _after_turn on a daemon thread; after stop() undoes
        # the patches it would walk the REAL board and write brief-only junk
        # sessions into data/sessions (observed leak, 2026-11-05). These hosts
        # test the WebUI, not dispatch.
        from pot import dispatch as dispatch_mod
        from pot import jobs as jobs_mod

        mp.setattr(dispatch_mod, "dispatch_pending", lambda run: 0)
        mp.setattr(jobs_mod, "flush", lambda sid: [])
        runtime = WebUIRuntime()
        return cls(make_webui_server(0, runtime), runtime, mp)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def open_webui(self, _loopback: bool = False) -> str:
        return self.base

    def webui_runtime(self):
        return self.runtime

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        from pot.server import clear_alerts

        clear_alerts()  # a stopped host leaves no ring behind (§61)
        self._mp.undo()


# --- Pot board engine fixtures (M1) ---
@pytest.fixture()
def repo(tmp_path):
    return RoleRepo(tmp_path / "roles")


@pytest.fixture()
def board(tmp_path, repo):
    return Board(tmp_path / "board.sqlite", repo)
