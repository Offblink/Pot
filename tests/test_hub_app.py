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
