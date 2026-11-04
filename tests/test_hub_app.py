"""Hub integration: real HTTP server, two simulated hosts over urllib."""

import socket
import urllib.error
import urllib.parse
import urllib.request

from pot.hub.app import Hub


def test_hub_binds_requested_port(room):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        fixed = probe.getsockname()[1]
    hub = Hub("srv", "room-token", room[0].store.root.parent, port=fixed)
    hub.start()
    try:
        assert hub.port == fixed
        # The requested port answers — via the session family that survived the
        # room cut (spec §10-3), on the loopback bind (§1.2).
        req = urllib.request.Request(f"http://127.0.0.1:{fixed}/api/sessions?token=room-token")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
    finally:
        hub.stop()


def test_bad_token_rejected(room):
    _hub, clients = room
    code, _out = clients["alpha"].post("/api/join", {"name": "alpha", "token": "wrong"})
    assert code == 403
    code, _out = clients["alpha"].get("/api/poll?host=alpha&token=wrong")
    assert code == 403


def test_sessions_api(room):
    _hub, clients = room
    code, _out = clients["alpha"].post(
        "/api/save",
        {
            "token": "room-token",
            "id": "s1",
            "title": "t",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert code == 200
    code, out = clients["alpha"].get("/api/sessions?token=room-token")
    assert out["sessions"][0]["id"] == "s1" and out["sessions"][0]["msgCount"] == 1
    code, out = clients["alpha"].get("/api/session?token=room-token&id=s1")
    assert out["messages"][0]["content"] == "hi"
    code, _out = clients["alpha"].post("/api/session/delete", {"token": "room-token", "id": "s1"})
    code, out = clients["alpha"].get("/api/sessions?token=room-token")
    assert out["sessions"] == []


def test_poll_route_stays_alive(room):
    """spec §10-3: /api/poll must survive the room-protocol cut (§1.2)."""
    _hub, clients = room
    code, out = clients["alpha"].poll_raw("alpha", after=0, timeout=0)
    assert code == 200
    assert out["messages"] == []
    assert isinstance(out["cursor"], int)


# ---- launcher API (spec §4.1): what the CMP host rides over loopback ----

import json  # noqa: E402
import os  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from pot.board import Board  # noqa: E402
from pot.roles import Actor, RoleRepo  # noqa: E402

TOKEN = "t0k"


@pytest.fixture()
def launcher(tmp_path):
    """A Hub with an injected tmp board/roles — never the process singletons."""
    roles = RoleRepo(tmp_path / "roles")
    roles.create({"id": "exec", "name": "执行者", "canClaim": ["coding"]}, "human")
    # the system Planner role production seeds (dispatch.roles_repo), mirrored
    # so /api/board's role listing is asserted against a realistic repo
    roles.create(
        {"id": "planner", "canCreateCard": True, "canClaim": False, "isTemplate": False}, "human"
    )
    board = Board(tmp_path / "board.sqlite", roles)
    hub = Hub("pot", TOKEN, tmp_path, board=board, roles=roles)
    hub.start()
    yield SimpleNamespace(hub=hub, board=board, roles=roles)
    hub.stop()


def _base(launcher) -> str:
    return f"http://127.0.0.1:{launcher.hub.port}"


def _get(launcher, path: str, token: str = TOKEN) -> tuple[int, dict]:
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(f"{_base(launcher)}{path}{sep}token={token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post(launcher, path: str, obj: dict, token: str = TOKEN) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{_base(launcher)}{path}",
        data=json.dumps({**obj, "token": token}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_host_status_answers_for_the_launcher(launcher):
    code, out = _get(launcher, "/api/host/status")
    assert code == 200 and out["ok"] is True
    assert out["pid"] == os.getpid()
    assert out["webui"] == ""  # filled only by run_server (stdout carries it too)
    assert isinstance(out["uptimeS"], float) and out["uptimeS"] >= 0
    assert out["version"]  # pot version string, non-empty


def test_board_create_list_complete_via_api(launcher):
    code, out = _post(
        launcher, "/api/board/create", {"title": "task", "labels": ["coding"], "priority": "urgent"}
    )
    assert code == 200 and out["ok"]
    card = out["card"]
    assert card["status"] == "todo" and card["createdBy"] == "human"

    code, out = _get(launcher, "/api/board")
    assert [c["id"] for c in out["cards"]] == [card["id"]]
    role_ids = {r["id"] for r in out["roles"]}
    assert {"exec", "planner"} <= role_ids  # system seed rides along

    # the engine still refuses a human ✓ outside review (gate 5 the other way)
    code, out = _post(launcher, "/api/board/complete", {"card_id": card["id"], "if_version": 1})
    assert code == 400 and "error" in out
    assert launcher.board.get(card["id"])["status"] == "todo"

    # reach review through the real agent gates, then the human accepts
    actor = Actor("exec", "s1")
    held = launcher.board.claim(actor, card["id"], card["ifVersion"])
    launcher.board.move(actor, card["id"], "review", held["ifVersion"])
    reviewed = launcher.board.get(card["id"])
    code, out = _post(
        launcher,
        "/api/board/complete",
        {"card_id": card["id"], "if_version": reviewed["ifVersion"]},
    )
    assert code == 200 and out["card"]["status"] == "done"

    # a stale token never reaches the board
    code, _out = _get(launcher, "/api/board", token="wrong")
    assert code == 403
    code, _out = _post(launcher, "/api/board/create", {"title": "x"}, token="wrong")
    assert code == 403


def test_board_assign_reject_and_stale_version(launcher):
    code, out = _post(launcher, "/api/board/create", {"title": "t", "labels": ["coding"]})
    card = out["card"]

    # assign to a role (and refuse one that does not exist)
    code, out = _post(
        launcher,
        "/api/board/assign",
        {"card_id": card["id"], "role": "exec", "if_version": card["ifVersion"]},
    )
    assert code == 200 and out["card"]["role"] == "exec"
    code, out = _post(
        launcher,
        "/api/board/assign",
        {"card_id": card["id"], "role": "ghost", "if_version": out["card"]["ifVersion"]},
    )
    assert code == 400 and "no_such_role" in out["error"]

    # stale write token rejected, state untouched (exact code pinned elsewhere)
    code, _out = _post(launcher, "/api/board/complete", {"card_id": card["id"], "if_version": 999})
    assert code == 400
    assert launcher.board.get(card["id"])["status"] == "todo"

    # reject works on a held card and lands the reason in the comments
    actor = Actor("exec", "s1")
    held = launcher.board.claim(actor, card["id"], launcher.board.get(card["id"])["ifVersion"])
    code, out = _post(
        launcher,
        "/api/board/reject",
        {"card_id": card["id"], "reason": "needs tests", "if_version": held["ifVersion"]},
    )
    assert code == 200 and out["card"]["status"] == "todo"
    assert any(c["text"] == "needs tests" for c in out["card"]["comments"])


def test_roles_crud_via_api(launcher):
    code, out = _post(
        launcher,
        "/api/roles/create",
        {"id": "tpl", "isTemplate": True, "tools": ["shell"], "wip": 1, "canCreateCard": False},
    )
    assert code == 200 and out["role"]["isTemplate"] is True

    # a human supplies its own fields (template derivation is the PLANNER's
    # path — pinned in tests/test_roles.py); the template merely exists
    code, out = _post(
        launcher, "/api/roles/create", {"id": "doc", "mission": "write", "tools": ["files"]}
    )
    assert code == 200
    assert out["role"]["tools"] == ["files"] and out["role"]["createdBy"] == "human"

    code, out = _post(launcher, "/api/roles/update", {"id": "doc", "mission": "write better"})
    assert code == 200 and out["role"]["mission"] == "write better"

    code, out = _get(launcher, "/api/roles")
    assert {"tpl", "doc"} <= {r["id"] for r in out["roles"]}

    code, _out = _post(launcher, "/api/roles/delete", {"id": "doc"})
    assert code == 200
    code, out = _get(launcher, "/api/roles")
    assert "doc" not in {r["id"] for r in out["roles"]}


def test_language_switch_writes_what_lang_js_serves(launcher):
    """spec §74: one switch, both halves — the launcher posts the language and the
    host (the file's only writer) puts it in config.json, which /lang.js re-reads
    on every request. status reports it back so the launcher can skip the write."""
    from pot import config as config_mod

    assert _get(launcher, "/api/host/status")[1]["ui_lang"] == "zh"  # the default

    code, out = _post(launcher, "/api/host/lang", {"lang": "en"})
    assert code == 200 and out["ui_lang"] == "en"
    assert config_mod.load_config().ui_lang == "en"
    written = json.loads(config_mod.CONFIG_PATH.read_text(encoding="utf-8"))
    assert written["ui_lang"] == "en"
    assert _get(launcher, "/api/host/status")[1]["ui_lang"] == "en"

    # Back to Chinese: the key leaves the file (zh is the default, config.py) and
    # the rest of the config is still there — the route must not blank the file.
    assert _post(launcher, "/api/host/lang", {"lang": "zh"})[0] == 200
    written = json.loads(config_mod.CONFIG_PATH.read_text(encoding="utf-8"))
    assert "ui_lang" not in written
    assert written["api_key"] == "k"


def test_language_switch_rejects_an_unknown_code(launcher):
    from pot import config as config_mod

    code, out = _post(launcher, "/api/host/lang", {"lang": "fr"})
    assert code == 400 and "error" in out
    assert config_mod.load_config().ui_lang == "zh"
