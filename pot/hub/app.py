"""Hub HTTP API, loopback-only: sessions + board/roles/host-status (spec §1.2/§4).

Token auth on every endpoint. The room-protocol family (join/leave/heartbeat/
send/fs), the friend/mail routes and the transfer routes are gone with the
rooms; what stays is the session store family plus the launcher's API
(spec §4.1: the CMP launcher rides /api/board/*, /api/roles/*,
/api/host/status over this loopback server).
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import dispatch, runlog
from ..config import UI_LANGS, load_config, local_version, save_config
from ..errors import PotError
from .asks import Asks
from .relay import Relay
from .roster import Roster
from .store import Store

MAX_BODY = 5 * 1024 * 1024
MAX_POLL = 25.0
# Sweep stale ask records. MUST exceed the longest waiter (the consent card
# held a clone for ask_timeout_s=1800): a swept record outlives its card,
# so a late click resolves nothing.
ASK_TIMEOUT = 1900.0
REAP_INTERVAL = 5.0
# Bytes per write on a download, and how often the delivery count is updated:
# 1 MiB is a page poll's worth of resolution (§49), and a multiple of the sizes
# a window is cut into (§50).


# How long a staging nobody finished is worth disk (§62). How much of a file
# proves it is the same file lives in landing — one definition, imported above.


def _query_int(params: dict, key: str) -> int | None:
    """A non-negative integer out of a query string, or None when it is not one."""
    raw = (params.get(key) or [""])[0].strip()
    return int(raw) if raw.isdigit() else None


class Hub:
    """Room server: roster + relay + asks + store behind one HTTP API."""

    def __init__(
        self,
        name: str,
        token: str,
        data_root: Path,
        heartbeat_timeout: float = 30.0,
        port: int = 0,
        board=None,
        roles=None,
    ):
        self.name = name
        self.token = token
        self._bind_port = port
        data_root = Path(data_root)
        self.roster = Roster(heartbeat_timeout)
        self.relay = Relay(name)
        self.asks = Asks()
        self.store = Store(data_root, self.asks)
        self._board = board  # None → the process-wide dispatch singletons
        self._roles = roles
        self.webui_url: str = ""  # filled by run_server for /api/host/status
        self._started = time.monotonic()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._reaper: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def board(self):
        return self._board if self._board is not None else dispatch.board()

    @property
    def roles(self):
        return self._roles if self._roles is not None else dispatch.roles_repo()

    def status(self) -> dict:
        """spec §4: what the launcher polls to see the host is alive (and to
        show model/version in settings)."""
        return {
            "ok": True,
            "pid": os.getpid(),
            "name": self.name,
            "version": local_version(),
            "uptimeS": round(time.monotonic() - self._started, 1),
            "webui": self.webui_url,
            # spec §74: the launcher's language switch is one control for both halves.
            # The launcher compares this with its own setting and writes through
            # /api/host/lang only when they differ, so a start is not a config write.
            "ui_lang": load_config().ui_lang,
        }

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("hub not started")
        return self._server.server_address[1]

    def start(self) -> None:
        handler = type("HubHandler", (_Handler,), {"hub": self})
        self._server = ThreadingHTTPServer(("127.0.0.1", self._bind_port), handler)
        self._server.daemon_threads = True
        runlog.note("hub listening on 127.0.0.1:%d as %r", self.port, self.name)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="pot-hub", daemon=True
        )
        self._thread.start()
        self._reaper = threading.Thread(target=self._reap_loop, name="pot-reaper", daemon=True)
        self._reaper.start()

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            runlog.note("hub on port %d stopped", self._server.server_address[1])
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _reap_loop(self) -> None:
        while not self._stop.wait(REAP_INTERVAL):
            for name in self.roster.reap():
                self.relay.drop_host(name)
            self.asks.sweep(ASK_TIMEOUT)

    # ── operations shared by handler, clones, and tests ──


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    hub: Hub = None  # type: ignore[assignment]

    def log_message(self, format: str, *args) -> None:
        pass  # quiet

    # ── plumbing ──

    def _reply(self, obj: dict, code: int = 200, headers: dict | None = None) -> None:
        data = json.dumps(obj).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Long-poll replies race client reconnects/disconnects all the
            # time; a gone reader is routine, not an error worth a traceback.
            self.close_connection = True

    def _bad_token(self) -> None:
        """Someone knocked with the wrong token — the host's half of "I cannot join".

        Throttled per caller: a client holding a stale token polls once a second,
        and the log is worth reading only if this is one line a minute. The route
        is logged without its query: on a GET the query *is* the token, and this
        file gets attached to bug reports (the repo is public).
        """
        peer = self.client_address[0]
        runlog.warn_once(
            f"hub-bad-token:{peer}",
            "hub: %s used the wrong token on %s — a friend holding an old token?",
            peer,
            self.path.split("?", 1)[0],
        )
        self._reply({"error": "bad token"}, 403)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("body too large")
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw or b"{}")
        if not isinstance(data, dict):
            raise ValueError("body must be an object")
        return data

    # ── routing ──

    def do_POST(self) -> None:
        try:
            url = urlparse(self.path)
            body = self._body()
            if body.get("token") != self.hub.token:
                self._bad_token()
                return
            path = url.path
            if path == "/api/save":
                self._save(body)
            elif path == "/api/session/delete":
                self._session_delete(body)
            # launcher board/roles API (spec §4.1) — human actions, human token
            elif path == "/api/board/create":
                self._reply(
                    {
                        "ok": True,
                        "card": self.hub.board.human_create(
                            str(body.get("title") or ""),
                            desc=str(body.get("desc") or ""),
                            labels=body.get("labels"),
                            priority=str(body.get("priority") or "normal"),
                            role=body.get("role"),
                            checklist=body.get("checklist"),
                            status=str(body.get("status") or "todo"),
                        ),
                    }
                )
            elif path == "/api/board/assign":
                self._reply(
                    {
                        "ok": True,
                        "card": self.hub.board.human_assign(
                            str(body.get("card_id") or ""),
                            body.get("role"),
                            body.get("if_version"),
                        ),
                    }
                )
            elif path == "/api/board/complete":
                self._reply(
                    {
                        "ok": True,
                        "card": self.hub.board.human_complete(
                            str(body.get("card_id") or ""), body.get("if_version")
                        ),
                    }
                )
            elif path == "/api/board/reject":
                self._reply(
                    {
                        "ok": True,
                        "card": self.hub.board.human_reject(
                            str(body.get("card_id") or ""),
                            str(body.get("reason") or ""),
                            body.get("if_version"),
                        ),
                    }
                )
            elif path == "/api/board/renew":
                self._reply(
                    {
                        "ok": True,
                        "card": self.hub.board.human_renew_lease(
                            str(body.get("card_id") or ""), body.get("if_version")
                        ),
                    }
                )
            elif path == "/api/board/delete":
                self._reply(
                    {
                        "ok": True,
                        "card": self.hub.board.human_delete(
                            str(body.get("card_id") or ""), body.get("if_version")
                        ),
                    }
                )
            elif path == "/api/roles/create":
                fields = {k: v for k, v in body.items() if k != "token"}
                self._reply({"ok": True, "role": self.hub.roles.create(fields, "human").to_dict()})
            elif path == "/api/roles/update":
                role_id = str(body.get("id") or "")
                fields = {k: v for k, v in body.items() if k not in ("token", "id")}
                self._reply(
                    {"ok": True, "role": self.hub.roles.update(role_id, fields, "human").to_dict()}
                )
            elif path == "/api/roles/delete":
                self.hub.roles.delete(str(body.get("id") or ""), "human")
                self._reply({"ok": True})
            # The launcher's language switch, other half (spec §74): config.json
            # `ui_lang` is what /lang.js serves to the WebUI, and the host process
            # owns that file and its lock — so the write happens here, not from
            # another process editing JSON behind the config lock's back.
            elif path == "/api/host/lang":
                lang = str(body.get("lang") or "")
                if lang not in UI_LANGS:
                    raise ValueError(f"lang must be one of {UI_LANGS}")
                cfg = load_config()
                cfg.ui_lang = lang
                save_config(cfg)
                self._reply({"ok": True, "ui_lang": lang})
            else:
                self._reply({"error": "not found"}, 404)
        except PotError as exc:
            self._reply({"error": str(exc)}, 400)
        except (ValueError, json.JSONDecodeError) as exc:
            self._reply({"error": str(exc)}, 400)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        params = parse_qs(url.query)
        token = (params.get("token") or [""])[0]
        if token != self.hub.token:
            self._bad_token()
            return
        try:
            if url.path == "/api/poll":
                self._poll(params)
            elif url.path == "/api/sessions":
                # 裁决 29: role sessions never surface to a user-facing list.
                rows = self.hub.store.sessions.list_sessions()
                self._reply({"sessions": [r for r in rows if not r.get("role")]})
            elif url.path == "/api/session":
                self._session_load(params)
            elif url.path == "/api/board":
                self._reply(
                    {
                        "cards": self.hub.board.list(),
                        "roles": [r.to_dict() for r in self.hub.roles.list(include_templates=True)],
                    }
                )
            elif url.path == "/api/roles":
                self._reply(
                    {"roles": [r.to_dict() for r in self.hub.roles.list(include_templates=True)]}
                )
            elif url.path == "/api/host/status":
                self._reply(self.hub.status())
            else:
                self._reply({"error": "not found"}, 404)
        except PotError as exc:
            self._reply({"error": str(exc)}, 400)

    def do_DELETE(self) -> None:
        # No DELETE routes survived the transfer cut.
        self._reply({"error": "not found"}, 404)

    # ── room ops ──

    # ── mail ──

    def _poll(self, params: dict) -> None:
        # Loopback-only (spec §1.2): no roster admission — /api/join is gone and
        # the token gates the caller. /api/poll must stay alive (§10-3).
        host = (params.get("host") or [""])[0]
        after = int((params.get("after") or ["0"])[0])
        timeout = min(float((params.get("timeout") or ["0"])[0]), MAX_POLL)
        inbox = self.hub.relay.host_buffer(host)
        messages, cursor = inbox.after(after, timeout)
        self._reply({"messages": [e.serialize() for e in messages], "cursor": cursor})

    # ── fs ops ──

    # ── sessions ──

    def _save(self, body: dict) -> None:
        store = self.hub.store.sessions
        store.save(
            str(body.get("id") or ""),
            str(body.get("title") or ""),
            body.get("messages") or [],
            body.get("subagents"),
            body.get("asks"),
        )
        self._reply({"ok": True})

    def _session_load(self, params: dict) -> None:
        sid = (params.get("id") or [""])[0]
        data = self.hub.store.sessions.load(sid)
        if data is None:
            self._reply({"error": "not found"}, 404)
            return
        self._reply(data)

    def _session_delete(self, body: dict) -> None:
        self.hub.store.sessions.delete(str(body.get("id") or ""))
        self._reply({"ok": True})

    # ── transfers ──
