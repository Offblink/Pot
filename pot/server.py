"""WebUI server: ThreadingHTTPServer + NDJSON streaming + static files from web/.

Single-host mode (spec §1.2): TriLayer is gone — turns build a Planner agent
(user sessions) or a resident role agent (sessions carrying a `role` key), and
work moves across the board (pot/dispatch.py). Host-driven turns (role dispatch,
job wakeups) reuse the same turn core with a tape-only sink, so a page watching
that session reattaches through /events exactly like a live chat turn.
"""

import contextlib
import json
import os
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pot import agents, dispatch, jobs, runlog, session
from pot.agent import SYSTEM_PROMPT, Agent, BoundTool, public_messages
from pot.config import (
    PROJECT_ROOT,
    RESOURCE_ROOT,
    UI_LANGS,
    load_config,
    remember_provider,
    save_config,
    switch_model,
)
from pot.errors import PotError
from pot.events import Sink
from pot.llm import probe_model
from pot.openfile import open_with_default, reveal_in_folder
from pot.plan import TODO_SCHEMA, PlanStore
from pot.tools.ask import resolve_ask
from pot.tools.mcp import mcp_extra_tools

WEB_DIR = RESOURCE_ROOT / "web"
PLANS_DIR = PROJECT_ROOT / "data" / "plans"  # one plan per session (裁决 17)
UPLOADS_DIR = PROJECT_ROOT / "data" / "uploads"  # drag-and-drop files (2026-11-06)

_mime = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".png": "image/png",
}


def _webui_token() -> str:
    """LAN access token: generated once and persisted, so QR codes and mobile
    bookmarks survive restarts."""
    path = Path.home() / ".pot" / "webui_token"
    try:
        t = path.read_text(encoding="utf-8").strip()
        if t:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(24)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(t, encoding="utf-8")
    except OSError:
        pass
    return t


WEBUI_TOKEN = _webui_token()


_TAPE_GRACE_S = 60.0  # how long a sealed (done) tape stays for late reattach


_STATIC_ROUTES = frozenset(
    (
        "/",
        "/app.js",
        "/common.js",
        "/style.css",
        "/motion.js",
        "/i18n.js",
        "/lang.js",
        "/favicon.png",
    )
)


def _int_or_none(value: str) -> int | None:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


RETRY_STRIP_PREFIXES = ("(LLM error:", "(Hit max tool rounds", "(Aborted")


def sanitize_for_retry(messages: list[dict]) -> list[dict]:
    """Drop the synthetic tail a failed turn left behind, so Alt+R continues
    from real context. Marker lines are recognized anywhere in the tail block;
    everything from the first marker on is discarded (tool calls without their
    results would poison the next completion)."""
    out = list(messages)
    while out:
        last = out[-1]
        content = last.get("content")
        if isinstance(content, str) and content.startswith(RETRY_STRIP_PREFIXES):
            out.pop()
            continue
        if last.get("role") == "assistant" and last.get("content") is None:
            out.pop()  # dangling tool_calls
            continue
        break
    return out


def repair_tool_gaps(messages: list[dict]) -> list[dict]:
    """Ensure every assistant tool_call is followed by a tool result.

    A turn that died between appending tool_calls and their results used to
    poison the saved session: the next completion request fails with HTTP 400
    (tool_calls must be answered), and the conversation is bricked from there
    on. Synthesize an explicit failure result for any unanswered call.
    """
    out: list[dict] = []
    unanswered: dict[str, str] = {}  # tool_call_id -> tool name
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            out.append(m)
            for tc in m["tool_calls"]:
                unanswered[str(tc.get("id"))] = str(
                    (tc.get("function") or {}).get("name") or "tool"
                )
            continue
        if role == "tool":
            unanswered.pop(str(m.get("tool_call_id")), None)
            out.append(m)
            continue
        if unanswered and role in ("user", "assistant"):
            # History gap: answer the dangling calls before moving on.
            for call_id, name in unanswered.items():
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": f"ERROR: turn was interrupted before {name} could run.",
                    }
                )
            unanswered = {}
        out.append(m)
    for call_id, name in unanswered.items():
        out.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": f"ERROR: turn was interrupted before {name} could run.",
            }
        )
    return out


def _plan_tool(session_id: str, sink: Sink) -> BoundTool:
    """The plan `todo` tool (裁决 17): full replace, saved with the session, and
    announced live so the chat card can strike finished items through."""
    store = PlanStore(PLANS_DIR)

    def _run(args: dict) -> str:
        try:
            plan, flipped = store.apply(session_id, args.get("items"))
        except PotError as exc:
            return f"ERROR: {exc}"
        session.set_plan(session_id, plan)
        sink.emit("plan", {"plan": plan, "flipped": flipped})
        return json.dumps({"ok": True, "plan": plan, "flipped": flipped}, ensure_ascii=False)

    return BoundTool(schema=TODO_SCHEMA, fn=_run)


class WebUIRuntime:
    """Turn/sessions/answer wiring for the WebUI. Default = single-host mode."""

    # Monotonic timestamp of the last WebUI HTTP request: the "is anyone
    # actually looking" signal. ask notifications fire only when this is
    # stale (nobody has the page open). Class attribute so a runtime built
    # without chaining __init__ still sees it; touch() shadows it per instance.
    last_seen: float = 0.0

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    def sessions_list(self) -> list[dict]:
        # 裁决 29: role sessions are the agents' memory, not the user's
        # conversations — the sidebar shows only the latter.
        return [s for s in session.list_sessions() if not s.get("role")]

    def sessions_load(self, session_id: str) -> dict | None:
        return session.load_session(session_id)

    def sessions_save(
        self,
        session_id: str,
        title: str,
        messages: list[dict],
        subagents: list | None = None,
        asks: list | None = None,
        plan: list | None = None,
        pinned: bool | None = None,
        role: str | None = None,
    ) -> None:
        session.save_session(
            session_id,
            title,
            messages,
            subagents=subagents,
            asks=asks,
            plan=plan,
            pinned=pinned,
            role=role,
        )

    def sessions_delete(self, session_id: str) -> None:
        session.delete_session(session_id)

    def sessions_pin(self, session_id: str, pinned: bool) -> None:
        session.set_pinned(session_id, pinned)

    def __init__(self, board=None, roles=None) -> None:
        """board/roles: injectable for tests; default = dispatch's singletons."""
        self._board = board
        self._roles = roles

    def board(self):
        return self._board if self._board is not None else dispatch.board()

    def roles_repo(self):
        return self._roles if self._roles is not None else dispatch.roles_repo()

    def new_session_id(self) -> str:
        return session.new_session_id()

    def new_session_prompt(self) -> str:
        # The turn runner rewrites the stored system row from
        # agent.system_prompt every turn (skills/diary are managed there);
        # this is what a brand-new session shows before its first turn.
        return SYSTEM_PROMPT + agents.PLANNER_ADDENDUM

    def build_agent(self, sink: Sink, should_abort) -> Agent:
        sid = getattr(sink, "session_id", None) or ""
        # 后台执行 (裁决 20): a fresh per-turn detach signal — the button sets
        # it, the running bash hands its process to the job table, the agent
        # clears it after the call that consumed it.
        tool_bg = threading.Event()
        _BG_TOOL_ABORTS[sid] = tool_bg

        def _abort() -> bool:
            return bool(should_abort and should_abort())

        cfg = load_config()
        stored = self.sessions_load(sid) if sid else None
        role_id = str((stored or {}).get("role") or "")
        role = None
        if role_id:
            try:
                role = self.roles_repo().get(role_id)
            except PotError as exc:
                runlog.problem("role session %s: %s (falls back to Planner)", sid, exc)
        if role is not None:
            agent = agents.build_role(
                cfg, sink, role=role, session_id=sid, board=self.board(), should_abort=_abort
            )
            # 计划 todo 挂角色会话（交接 M2b）: the plan card belongs to the
            # session doing the work, not to the conversation that dispatched it.
            agent.extra_tools["todo"] = _plan_tool(sid, sink)
        else:
            agent = agents.build_planner(
                cfg, sink, session_id=sid, board=self.board(), should_abort=_abort
            )
        agent.tool_abort_event = tool_bg
        return agent

    def route_answer(self, ask_id: str, value: str | list[str]) -> bool:
        """Resolve an /answer submission. Default: in-process inquire only."""
        return resolve_ask(ask_id, value)

    def pending_asks(self) -> list[dict]:
        """Out-of-band asks: none in single-host mode — asks ride the live
        stream and the answer route resolves them in-process."""
        return []

    def mcp_tools(self) -> dict:
        return mcp_extra_tools(load_config().mcp_servers)


# Interrupt support: one Event per running turn, keyed by session id. /stop
# sets them; the agent checks between rounds and on every SSE line read.
_ACTIVE_TURNS: dict[str, set[threading.Event]] = {}
_TURNS_LOCK = threading.Lock()

# One writer per session: a same-session turn started while another is still
# finishing would otherwise overwrite its saved context (last-writer-wins).
_SESSION_LOCKS: dict[str, threading.Lock] = {}
_SESSION_LOCKS_GUARD = threading.Lock()

# 后台执行 detach signal (裁决 20): one Event per running turn — the button
# sets it, the running bash hands its process to the job table (pot/jobs.py),
# the agent clears it after the call that consumed it. Distinct from
# _ACTIVE_TURNS (which ends the turn) — the agent loop's stop path never reads it.
_BG_TOOL_ABORTS: dict[str, threading.Event] = {}

# Tombstones for sessions deleted while a turn was still running: the turn's
# exit-path save must not resurrect the file the user just deleted.
_TURN_DELETED: set[str] = set()

# Per-turn event tapes: the WebSink records every event it emits so a client
# that reloads mid-turn can reattach via /events and replay what it missed.
# A tape lives until its turn's done marker is consumed / grace-popped.
_TURN_TAPES: dict[str, list[dict]] = {}


def _session_lock(session_id: str) -> threading.Lock:
    with _SESSION_LOCKS_GUARD:
        return _SESSION_LOCKS.setdefault(session_id, threading.Lock())


# ── session alerts (§61): what wants the user's eyes ──
#
# Four things in a session want the user: the agent asked a question (an
# in-turn `ask`), a turn finished, a turn failed, and a completion card block
# landed (裁决 30). An alert is raised only when
# nobody is *showing* that session: the page that has it open — visible and
# focused, because a minimized webUI is not "opened" (user rule, 2026-09-21)
# — says so every few seconds, and the server reads a fresh claim as "the user
# is watching". A hidden or unfocused page sends nothing, its claim goes stale,
# and the next event is real: the red dot rides /sessions. Opening the session
# is what stops it — the shape of the unread-mail ring (§25.2), with the page's
# own claim in place of the grace.

ALERT_KINDS = ("ask", "done", "error", "card")
SEEN_TTL_S = 8.0  # a claim reads as "watching" this long (page heartbeat: 3 s)
_ALERTS: dict[str, str] = {}  # session id -> kind ("ask" | "done" | "error" | "card")
_SEEN: dict[str, float] = {}  # session id -> monotonic of the last claim
_ALERT_LOCK = threading.Lock()


def note_alert(session_id: str | None, kind: str) -> None:
    """Raise a session's alert, unless a page is showing it right now."""
    if not session_id or kind not in ALERT_KINDS:
        return
    with _ALERT_LOCK:
        seen = _SEEN.get(session_id)
        if seen is not None and time.monotonic() - seen <= SEEN_TTL_S:
            return
        _ALERTS[session_id] = kind


def session_alerts() -> dict[str, str]:
    """A copy of the outstanding alerts, session id -> kind (the GUI rings on it)."""
    with _ALERT_LOCK:
        return dict(_ALERTS)


def forget_session(session_id: str) -> None:
    """Drop a session's alert and claim (it was deleted)."""
    with _ALERT_LOCK:
        _ALERTS.pop(session_id, None)
        _SEEN.pop(session_id, None)


def clear_alerts() -> None:
    """Forget every alert and claim: a stopped room leaves no ring behind."""
    with _ALERT_LOCK:
        _ALERTS.clear()
        _SEEN.clear()


def mark_seen(session_id: str, visible: bool) -> dict[str, str]:
    """A page's report about the session it is showing.

    `visible` claims it (and drops its alert); otherwise the claim is released
    — the page switched away, or went hidden. Either way the answer is the
    alert map, so one request carries both the heartbeat and the red dots.
    """
    with _ALERT_LOCK:
        if session_id:
            if visible:
                _SEEN[session_id] = time.monotonic()
                _ALERTS.pop(session_id, None)
            else:
                _SEEN.pop(session_id, None)
        return dict(_ALERTS)


def unanswered_asks(asks: list[dict] | None) -> bool:
    """A turn that ends holding an unanswered ask still wants the user (§61)."""
    return any(str(ask.get("status") or "") != "answered" for ask in asks or [])


class WebSink:
    """Thread-safe NDJSON writer over the /chat response stream.

    `handler=None` is the host-driven shape (role dispatch, job wakeups): the
    event tape still records — so /events reattaches exactly as for a chat
    turn — but there is no HTTP stream to write to.
    """

    def __init__(self, handler: "YesSirHandler | None", session_id: str | None = None):
        self.handler = handler
        self.session_id = session_id
        self.closed = False

    def emit(self, kind: str, content) -> None:
        if self.session_id is not None and kind != "done":
            # Record for /events reattach; the done marker is appended by the
            # turn's exit path so replay consumers never miss tail events.
            with _TURNS_LOCK:
                tape = _TURN_TAPES.get(self.session_id)
                if tape is not None:
                    tape.append({"type": kind, "content": content})
        if kind == "ask":
            # The agent is blocked on an answer: an ask that nobody watches is
            # raised right here, mid-turn (it can sit for ASK_TIMEOUT_S).
            note_alert(self.session_id, "ask")
        if self.closed or self.handler is None:
            return
        try:
            data = json.dumps({"type": kind, "content": content}, ensure_ascii=False)
            self.handler.wfile.write((data + "\n").encode("utf-8"))
            self.handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            self.closed = True


class YesSirHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    runtime: WebUIRuntime = None  # type: ignore[assignment]

    # ---- plumbing ---------------------------------------------------------
    def log_message(self, fmt, *args):  # quiet
        pass

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _answer(self, routes) -> None:
        """Every request gets an answer — a route that blows up says so.

        A dropped connection is indistinguishable from a network failure in the
        browser, and Chromium then silently RE-SENDS the POST: a route that
        raised before replying left /comm-send unanswered, the send-file modal
        said "Failed to fetch", and each re-send restarted its bar from zero
        (spec §47). So a route exception becomes a 500 the page can print, and
        a dead reader is just closed (nothing left to say to it).
        """
        try:
            routes()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception as exc:  # the point is to answer, not to type the failure
            runlog.problem("webui %s %s failed: %s", self.command, self.path.split("?")[0], exc)
            self.close_connection = True
            with contextlib.suppress(Exception):  # already streaming: no reply room
                self._send_json({"error": f"{type(exc).__name__}: {exc}"}, status=500)

    def _authorized(self) -> bool:
        """Loopback clients (desktop WebUI, GUI) pass freely. LAN clients must
        carry the QR token for every data route. Static shell assets (page,
        css, js) stay open: they carry no data, their sub-resource URLs cannot
        append ?t=, and a phone opening /m without a valid token then gets a
        working page whose m.js shows the rescan overlay — not a broken
        half-styled one."""
        if self.client_address[0] in ("127.0.0.1", "::1"):
            return True
        route = urlparse(self.path).path
        if route in _STATIC_ROUTES:
            return True
        if route.startswith("/vendor/") and "/" not in route[8:] and ".." not in route:
            return True  # flat vendor dir; same guard as the route itself
        q = parse_qs(urlparse(self.path).query)
        return (q.get("t") or [""])[0] == WEBUI_TOKEN

    def _gate(self) -> bool:
        if self._authorized():
            return True
        self._send_json({"error": "unauthorized — rescan the QR code"}, status=403)
        return False

    def _send_static(self, filename: str) -> None:
        path = WEB_DIR / filename
        if not path.is_file():
            self._send_json({"error": "not found"}, status=404)
            return
        body = path.read_bytes()
        mime = _mime.get(path.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---- GET --------------------------------------------------------------
    def do_GET(self):
        self._answer(self._get_routes)

    def _get_routes(self):
        if not self._gate():
            return
        self.runtime.touch()  # anyone still polling = someone is looking
        url = urlparse(self.path)
        route = url.path
        if route == "/":
            self._send_static("index.html")
        elif route in (
            "/app.js",
            "/common.js",
            "/style.css",
            "/motion.js",
            "/i18n.js",
            "/favicon.png",
        ):
            self._send_static(route.lstrip("/"))
        elif route == "/lang.js":
            # The launcher's settings page owns the language (§74). Read on every
            # request so a change takes effect on the next page load instead of
            # needing the room restarted.
            lang = load_config().ui_lang
            if lang not in UI_LANGS:
                lang = "zh"
            body = f"window.POT_LANG = {json.dumps(lang)};".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif (
            route.startswith("/vendor/") and "/" not in route[8:] and ".." not in route
        ):  # flat vendor dir; no traversal
            self._send_static(route[1:])  # web/vendor/<file> — keep the dir prefix
        elif route == "/model":
            cfg = load_config()
            # `endpoint` rides along since §68 (switching a model switches the url too);
            # the key never goes to the page — it has no use for it and the config modal
            # is the one place a user types it.
            self._send_json(
                {"model": cfg.model, "models": cfg.model_list, "endpoint": cfg.endpoint}
            )
        elif route == "/config-status":
            self._send_json({"configured": load_config().configured})
        elif route == "/asks":
            self._send_json({"asks": self.runtime.pending_asks()})
        elif route == "/sessions":
            sessions = self.runtime.sessions_list()
            alerts = session_alerts()
            for entry in sessions:
                # §61: the red dot — what the session wants, or None for quiet.
                entry["alert"] = alerts.get(str(entry.get("id")))
            # Stable sort: pinned sessions float, each group keeps recency order.
            sessions.sort(key=lambda entry: not entry.get("pinned"))
            with _TURNS_LOCK:
                for s in sessions:
                    tape = _TURN_TAPES.get(str(s.get("id")))
                    s["running"] = tape is not None and not any(
                        ev.get("type") == "done" for ev in tape
                    )
            self._send_json({"sessions": sessions})
        elif route == "/session":
            params = parse_qs(url.query)
            session_id = (params.get("id") or [None])[0]
            data = self.runtime.sessions_load(session_id) if session_id else None
            if data is None:
                self._send_json({"error": "not found"}, status=404)
                return
            after = _int_or_none((params.get("after") or [""])[0])
            if after is None:
                self._send_json(data)
            else:
                # `after=N`: only the rows added since the caller's cursor, so a
                # page watching for new transfers can append them instead of
                # repainting the transcript (which flickers: the scrollbar, the
                # selection, the images — §55).
                messages = data.get("messages") or []
                self._send_json(
                    {
                        "id": data.get("id"),
                        "title": data.get("title"),
                        "messages": messages[max(0, after) :],
                        "total": len(messages),
                    }
                )
        elif route == "/events":
            self._handle_events((parse_qs(url.query).get("sessionId") or [None])[0])
        elif route == "/jobs":
            sid = (parse_qs(url.query).get("sessionId") or [None])[0]
            self._send_json({"jobs": jobs.list_jobs(sid)})
        elif route == "/board":
            # The scene's whole data feed (裁决 36): cards + roles + the mounted
            # role instances with what each is holding. Loopback-gated like
            # every data route.
            cards = self.runtime.board().list()
            instances = []
            for row in session.list_sessions():
                rid = row.get("role")
                if not rid:
                    continue  # conversations are not agents (裁决 29)
                sid = str(row.get("id") or "")
                held = [c for c in cards if c.get("holder") == f"{rid}:{sid}"]
                stuck = any(c.get("status") == "blocked" for c in held)
                working = any(c.get("status") == "doing" for c in held)
                instances.append(
                    {
                        "role": rid,
                        "session": sid,
                        "number": int(row.get("instance") or 1),
                        "status": "stuck" if stuck else ("working" if working else "idle"),
                        "cards": [c["id"] for c in held],
                    }
                )
            instances.sort(key=lambda x: (x["role"], x["number"]))
            self._send_json(
                {
                    "cards": cards,
                    "roles": [
                        r.to_dict() for r in self.runtime.roles_repo().list(include_templates=True)
                    ],
                    "instances": instances,
                }
            )
        else:
            self._send_json({"error": "not found"}, status=404)

    # ---- POST -------------------------------------------------------------
    def do_POST(self):
        self._answer(self._post_routes)

    def _post_routes(self):
        if not self._gate():
            return
        self.runtime.touch()
        url = urlparse(self.path)
        if url.path == "/chat":
            self._handle_chat()
        elif url.path == "/retry":
            self._handle_retry()
        elif url.path == "/stop":
            data = self._read_body()
            sid = str(data.get("sessionId") or "")
            with _TURNS_LOCK:
                events = _ACTIVE_TURNS.pop(sid, set())
            for event in events:
                event.set()
            self._send_json({"ok": bool(events)})
        elif url.path == "/background-tool":
            # 后台执行 (裁决 20): set the session's detach signal. The running
            # bash picks it up within its 0.2s wait loop, hands its LIVE process
            # to the job table (no kill, no re-run), and returns BACKGROUNDED
            # with the job id; the output rides /jobs polling and a [job report]
            # wake. We deliberately do NOT reuse /stop — that would kill the
            # very process the job is about to adopt.
            data = self._read_body()
            sid = str(data.get("sessionId") or "")
            with _TURNS_LOCK:
                tool_ev = _BG_TOOL_ABORTS.get(sid)
            if tool_ev is not None:
                tool_ev.set()
            self._send_json({"ok": tool_ev is not None})
        elif url.path == "/jobs/kill":
            data = self._read_body()
            ok = jobs.kill(str(data.get("id") or ""))
            self._send_json({"ok": ok}, status=200 if ok else 404)
        elif url.path == "/board/create":
            # 人建卡（裁决 37: the launcher board page is gone — the WebUI's
            # center board posts here).
            data = self._read_body()
            try:
                card = self.runtime.board().human_create(
                    str(data.get("title") or ""),
                    desc=str(data.get("desc") or ""),
                    labels=data.get("labels"),
                    priority=str(data.get("priority") or "normal"),
                    role=str(data.get("role") or "") or None,
                    checklist=data.get("checklist"),
                )
            except PotError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"ok": True, "card": card})
        elif url.path == "/board/reopen":
            # 裁决 32: the human's board action — done → todo, reason in comments.
            data = self._read_body()
            try:
                card = self.runtime.board().human_reopen(
                    str(data.get("card_id") or ""),
                    str(data.get("reason") or ""),
                    data.get("if_version"),
                )
            except PotError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"ok": True, "card": card})
        elif url.path == "/board/delete":
            data = self._read_body()
            try:
                card = self.runtime.board().human_delete(
                    str(data.get("card_id") or ""), data.get("if_version")
                )
            except PotError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json({"ok": True, "card": card})
        elif url.path == "/answer":
            data = self._read_body()
            value = data.get("value")
            if isinstance(value, list):
                value = [str(v) for v in value]
            else:
                value = str(value or "")
            ok = self.runtime.route_answer(str(data.get("id") or ""), value)
            self._send_json({"ok": ok}, status=200 if ok else 404)
        elif url.path == "/session/seen":
            # §61: the page's claim about what it is showing (and the answer is
            # every outstanding alert, which is what paints the sidebar's dots).
            data = self._read_body()
            self._send_json(
                {"alerts": mark_seen(str(data.get("id") or ""), bool(data.get("visible")))}
            )
        elif url.path == "/pin":
            data = self._read_body()
            sid = str(data.get("id") or "")
            if not sid or self.runtime.sessions_load(sid) is None:
                self._send_json({"error": "not found"}, status=404)
                return
            self.runtime.sessions_pin(sid, bool(data.get("pinned")))
            self._send_json({"ok": True})
        elif url.path == "/model":
            # spec §66: the header's dropdown calls this. Switching is a write
            # plus one tiny completion — the page is told both facts separately,
            # because "saved" and "and it answers" are not the same claim.
            name = str(self._read_body().get("model") or "").strip()
            if not name:
                self._send_json({"ok": False, "detail": "no model given"}, status=400)
                return
            cfg = load_config()
            fresh = switch_model(cfg, name)  # §68: 连带把名字自己的端点+密钥带过来
            save_config(cfg)
            reachable, detail = probe_model(cfg.model, cfg.endpoint, cfg.api_key)
            if reachable and remember_provider(cfg, cfg.model, cfg.endpoint, cfg.api_key):
                # 这次调用回 200 了: 把它用的那套 url+key 记在这个名字上 (§68).
                save_config(cfg)
            runlog.note("model switched to %s (new=%s, reachable=%s)", cfg.model, fresh, reachable)
            self._send_json(
                {
                    "ok": True,
                    "model": cfg.model,
                    "models": cfg.model_list,
                    "endpoint": cfg.endpoint,
                    "fresh": fresh,
                    "reachable": reachable,
                    "detail": detail,
                }
            )
        elif url.path == "/configure":
            data = self._read_body()
            cfg = load_config()
            if data.get("model"):
                # §66: the modal's Model box adds to the pickable list instead of
                # overwriting the one in use — the header's dropdown reads the same
                # list, so a name typed once is one click away afterwards.
                # §68: switching first lets a remembered pairing fill the file; the
                # values typed into this very form then win over it (that is what
                # "the user said so" means here).
                switch_model(cfg, str(data["model"]))
            if data.get("api_key"):
                cfg.api_key = data["api_key"]
            if data.get("endpoint"):
                cfg.endpoint = data["endpoint"]
            # 手填的这套就是这个模型的端点+密钥 (§68): 记在名字上, 切走再切回来它自己跟上.
            remember_provider(cfg, cfg.model, cfg.endpoint, cfg.api_key)
            save_config(cfg)
            self._send_json({"ok": True, "models": cfg.model_list})
        elif url.path == "/save":
            data = self._read_body()
            existing = self.runtime.sessions_load(data.get("id", ""))
            if existing is None:
                self._send_json({"ok": False}, status=400)
                return
            self.runtime.sessions_save(
                data["id"],
                data.get("title") or existing.get("title") or "",
                existing.get("messages", []),
                subagents=existing.get("subagents", []),
                asks=existing.get("asks", []),
            )
            self._send_json({"ok": True})
        elif url.path == "/new":
            session_id = self.runtime.new_session_id()
            self.runtime.sessions_save(
                session_id,
                "(new session)",
                [{"role": "system", "content": self.runtime.new_session_prompt()}],
            )
            self._send_json({"id": session_id, "title": "(new session)"})
        elif url.path == "/pickfile":
            self._handle_pickfile()
        elif url.path == "/upload":
            self._handle_upload()
        elif url.path == "/open":
            self._handle_open()
        else:
            self._send_json({"error": "not found"}, status=404)

    # ---- DELETE -----------------------------------------------------------
    def do_DELETE(self):
        self._answer(self._delete_routes)

    def _delete_routes(self):
        if not self._gate():
            return
        url = urlparse(self.path)
        if url.path == "/session":
            session_id = (parse_qs(url.query).get("id") or [None])[0]
            if session_id:
                with _TURNS_LOCK:
                    events = _ACTIVE_TURNS.pop(session_id, set())
                    if events:
                        # A turn still runs in this session: abort it and
                        # tombstone the id so its exit-path save cannot
                        # resurrect the file the user just deleted.
                        _TURN_DELETED.add(session_id)
                for event in events:
                    event.set()
                self.runtime.sessions_delete(session_id)
                forget_session(session_id)  # a deleted session has nothing to ring for
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found"}, status=404)

    def _handle_chat(self) -> None:
        data = self._read_body()
        session_id = data.get("sessionId")
        self._run_turn(session_id, user_msg=str(data.get("message") or ""))

    def _handle_retry(self) -> None:
        """Alt+R: rerun the last turn with no new prompt, continuing from real
        context (synthetic error tail is stripped; see sanitize_for_retry)."""
        data = self._read_body()
        session_id = data.get("sessionId")
        stored = self.runtime.sessions_load(session_id) if session_id else None
        if not stored:
            self._send_json({"error": "no session to retry"}, status=400)
            return
        messages = sanitize_for_retry(stored["messages"])
        if not any(m.get("role") != "system" for m in messages):
            self._send_json({"error": "nothing to retry"}, status=400)
            return
        self._run_turn(session_id, user_msg=None, messages=messages)

    def _run_turn(
        self,
        session_id: str | None,
        user_msg: str | None,
        messages=None,
    ) -> None:
        if messages is None and not session_id:
            # Generate before registering: /stop keys on the real session id.
            session_id = self.runtime.new_session_id()
        sink = WebSink(self, session_id)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.close_connection = True
        try:
            _execute_turn(session_id, user_msg, messages=messages, sink=sink, runtime=self.runtime)
        finally:
            with contextlib.suppress(Exception):  # stream may already be gone
                self.wfile.flush()

    def _handle_events(self, session_id: str | None) -> None:
        """Reattach to a (recently) running turn: replay its recorded events,
        then live-stream new ones until the tape's done marker. A missing tape
        means nothing is running — answer with a bare done so the client
        simply reloads from disk."""
        if not session_id:
            self._send_json({"error": "need sessionId"}, status=400)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.close_connection = True
        idx = 0
        try:
            while True:
                with _TURNS_LOCK:
                    tape = _TURN_TAPES.get(session_id)
                    fresh = tape[idx:] if tape is not None else []
                    idx += len(fresh)
                try:
                    for ev in fresh:
                        self.wfile.write(
                            (json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8")
                        )
                    if fresh:
                        self.wfile.flush()
                        if any(ev.get("type") == "done" for ev in fresh):
                            return
                    elif tape is None:
                        self.wfile.write(b'{"type": "done", "content": null}\n')
                        self.wfile.flush()
                        return
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
                time.sleep(0.2)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _handle_open(self) -> None:
        """A card's two actions (spec §73): open the file, or show it in its folder.

        The page lives in a browser and cannot launch anything, so a click
        travels here and this host does what a double-click would. The standing
        is /download's: the WebUI token means "the owner's own device" (the
        phone that scanned the QR), and a caller holding it can already drive
        the agent, whose local tools run shell commands — so this adds a shorter
        path to that, not a new kind of access. What it must not do is launch a
        path that is not there: a stale card is a 404, never an attempt.
        """
        data = self._read_body()
        raw = str(data.get("path") or "")
        action = str(data.get("action") or "open")
        if not raw:
            self._send_json({"error": "missing path"}, status=400)
            return
        if action not in ("open", "reveal"):
            self._send_json({"error": f"unknown action: {action}"}, status=400)
            return
        target = Path(raw)
        if not target.is_absolute():
            target = PROJECT_ROOT / target  # same rule as /download
        if not target.exists():
            self._send_json({"error": f"no such file: {raw}"}, status=404)
            return
        launcher = reveal_in_folder if action == "reveal" else open_with_default
        result = launcher(target)
        # The log is where "点了没反应" gets diagnosed: raised=False is the
        # honest answer for a window that only reached the taskbar.
        runlog.note("webui %s %s (raised=%s)", action, target, result.get("raised"))
        self._send_json({"ok": True, "action": action, **result})

    def _handle_pickfile(self) -> None:
        try:
            import tkinter as tk  # noqa: PLC0415 (heavy GUI import, only on demand)
            from tkinter import filedialog  # noqa: PLC0415

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(title="Select a file")
            root.destroy()
            self._send_json({"path": path or None})
        except Exception as exc:
            self._send_json({"path": None, "error": str(exc)})

    def _handle_upload(self) -> None:
        """Drag-and-drop (2026-11-06): the body IS the file, saved under
        data/uploads/<name>. Raw bytes on purpose — the stdlib has no multipart
        parser, and a same-origin POST carries no CORS story. The name is
        basenamed (both separators) so a crafted ?name= can never escape the
        directory; the body streams to disk so a big drop costs no memory."""
        name = (parse_qs(urlparse(self.path).query).get("name") or [""])[0]
        safe = Path(name.replace("\\", "/")).name
        safe = "".join(ch for ch in safe if ch not in '<>:"|?*' and ord(ch) >= 32).rstrip(". ")
        if not safe or safe in (".", ".."):
            self.close_connection = True  # the body stays unread: do not keep-alive
            self._send_json({"error": "bad name"}, status=400)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            self._send_json({"error": "empty body"}, status=400)
            return
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        path = UPLOADS_DIR / safe
        try:
            remaining = length
            with path.open("wb") as fh:
                while remaining:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    fh.write(chunk)
                    remaining -= len(chunk)
        except Exception:
            with contextlib.suppress(OSError):
                path.unlink()  # a torn drop is not a file
            raise
        self._send_json({"ok": True, "path": str(path)})


# The runtime host-driven turns (role dispatch, job wakeups) run against: the
# one server this process serves (installed by make_webui_server). Dict-held so
# it is mutated, never rebound (no global statement).
_HOST: dict = {}


def host_turn(session_id: str, user_msg: str | None, *, internal: bool = False) -> None:
    """A turn with no HTTP client behind it (spec: role dispatch, job
    wakeups): the same core with a tape-only sink, so a page watching that
    session reattaches through /events exactly like a live chat turn.
    `internal=True` marks the input as a host note (裁决 35: persisted with the
    flag, never rendered — only the model reads it)."""
    runtime = _HOST.get("runtime") or WebUIRuntime()
    _execute_turn(
        session_id, user_msg, sink=WebSink(None, session_id), runtime=runtime, internal=internal
    )


def deliver_card_block(session_id: str, cards: list[dict]) -> None:
    """裁决 30: write the completion card block straight into the dispatching
    conversation — no model turn, no internal note.

    The session lock serializes against chat turns: a turn holds it from load
    to save, so an append made under it can never be clobbered by a save that
    loaded earlier, and a queued write simply lands after the turn's reply.
    """
    lang = "en" if load_config().ui_lang == "en" else "zh"
    block = dispatch.done_block(cards, lang)
    with _session_lock(session_id):
        data = session.load_session(session_id)
        if data is None:  # deleted since dispatch: nothing to tell
            return
        messages = list(data.get("messages") or [])
        messages.append({"role": "assistant", "content": block, "ts": time.time()})
        session.save_session(
            session_id,
            str(data.get("title") or ""),
            messages,
            data.get("subagents"),
            data.get("asks"),
        )
    runlog.note("done: card block -> %s (%d card(s))", session_id, len(cards))
    note_alert(session_id, "card")


def _after_turn(session_id: str, aborted: bool) -> None:
    """Post-turn hooks: deliver jobs that finished while this turn ran (spec
    §3.4 裁决 20 — 挂起补投), wake roles for claimable cards (M2b), and write
    completion card blocks into the conversations that dispatched them (裁决 30/31).
    A stopped turn does none of it — stop means stop."""
    try:
        # Snapshot first: a card that reaches done or blocked inside the flush
        # or the dispatch cycle below counts as fresh for THIS hook.
        before_done = dispatch.cards_done()
        before_blocked = dispatch.cards_blocked()
        pending = jobs.flush(session_id)
        if pending:
            host_turn(session_id, "\n\n".join(jobs.report(j) for j in pending), internal=True)
        if aborted:
            return
        dispatch.dispatch_pending(host_turn)
        fresh_done = dispatch.cards_done() - before_done
        if fresh_done:
            cards = [dispatch.board().get(cid) for cid in sorted(fresh_done)]
            lang = "en" if load_config().ui_lang == "en" else "zh"
            for target, routed in dispatch.notify_route(cards).items():
                deliver_card_block(target, routed)
                # 裁决 38: after the block, wake the source conversation's
                # Planner internally (35) — review the report, split what's next.
                host_turn(target, dispatch.done_note(routed, lang), internal=True)
        # 裁决 34: a card going blocked wakes its planner — internally (35).
        fresh_blocked = dispatch.cards_blocked() - before_blocked
        if fresh_blocked:
            cards = [dispatch.board().get(cid) for cid in sorted(fresh_blocked)]
            lang = "en" if load_config().ui_lang == "en" else "zh"
            for target, routed in dispatch.notify_route(cards).items():
                host_turn(target, dispatch.stuck_note(routed, lang), internal=True)
    except Exception as exc:
        runlog.problem("after-turn %s: %s", session_id, exc)


def _execute_turn(
    session_id: str | None,
    user_msg: str | None,
    *,
    sink: WebSink,
    runtime: WebUIRuntime,
    messages=None,
    internal: bool = False,
) -> None:
    """The turn core, shared by HTTP chat turns and host-driven turns:
    register /stop → queue behind the session lock → load → run → save →
    alert → seal the tape → schedule the after-turn hooks."""
    if messages is None and not session_id:
        session_id = runtime.new_session_id()
    abort_event = threading.Event()
    with _TURNS_LOCK:
        _ACTIVE_TURNS.setdefault(session_id, set()).add(abort_event)
    try:
        if _session_lock(session_id).locked():
            # A queued turn must not look dead: say why nothing streams yet.
            sink.emit("status", "Waiting for the still-running turn in this session...")
        with _session_lock(session_id):
            # Load context inside the lock: a queued turn must continue
            # from the previous turn's persisted reply, not a snapshot
            # taken before the wait (which dropped that reply on save).
            stored = runtime.sessions_load(session_id) if session_id else None
            if messages is None:
                if stored:
                    messages = list(stored["messages"])
                else:
                    messages = [{"role": "system", "content": runtime.new_session_prompt()}]
                if user_msg is not None:
                    row: dict = {"role": "user", "content": user_msg}
                    if internal:
                        # 裁决 35: a host note the model must read but the
                        # renderer must never show.
                        row["internal"] = True
                    messages.append(row)
            messages = repair_tool_gaps(messages)

            # Persist at turn start: the user message must be on disk while
            # the turn streams. Otherwise a refresh mid-turn shows an empty
            # session and invites chatting into / deleting one that is busy.
            prior = (stored or {}).get("subagents", []) if isinstance(stored, dict) else []
            prior_asks = (stored or {}).get("asks", []) if isinstance(stored, dict) else []
            # A role session keeps its mounted title (the card brief that wakes
            # it would otherwise become the sidebar label on the first save);
            # plain sessions derive the title from their first message as before.
            if str((stored or {}).get("role") or ""):
                title = str((stored or {}).get("title") or "") or session.get_session_title(
                    messages
                )
            else:
                title = session.get_session_title(messages)
            runtime.sessions_save(
                session_id,
                title,
                public_messages(messages),
                subagents=prior,
                asks=prior_asks,
            )
            # Start recording after the queue wait: a queued turn must not
            # clobber the still-running turn's tape for the same session.
            with _TURNS_LOCK:
                _TURN_TAPES[session_id] = []
            agent = runtime.build_agent(sink, abort_event.is_set)
            fresh_prompt = getattr(agent, "system_prompt", None)
            if fresh_prompt and messages and messages[0].get("role") == "system":
                # The system row is host-managed: the rebuilt prompt (Planner
                # addendum, live role mission, skills) must reach the model —
                # a row frozen at session creation would pin the retired
                # trilayer prompt forever.
                messages[0] = {"role": "system", "content": fresh_prompt}
            jobs.set_current_session(session_id)
            try:
                agent.run(messages)
            finally:
                jobs.set_current_session(None)
                # Persist on every exit path (success, abort, crash): a
                # turn that never saves is a turn whose context is lost.
                new_asks = list(getattr(agent, "asks", None) or [])
                with _TURNS_LOCK:
                    resurrects = session_id in _TURN_DELETED
                    if resurrects:
                        _TURN_DELETED.discard(session_id)
                if not resurrects:
                    runtime.sessions_save(
                        session_id,
                        title,
                        public_messages(messages),
                        subagents=prior,
                        asks=prior_asks + new_asks,
                    )
        # §61: a finished turn is news — unless the user stopped it (they
        # were right there) or deleted the session under it. note_alert
        # drops it anyway while a page is showing that session.
        if not resurrects and not abort_event.is_set():
            note_alert(session_id, "ask" if unanswered_asks(new_asks) else "done")
        sink.emit("sessionId", session_id)
        sink.emit("done", None)
    except Exception as exc:
        if not abort_event.is_set():  # a stopped turn must not ring, however it ended
            note_alert(session_id, "error")
        sink.emit("error", str(exc))
        sink.emit("done", None)
    finally:
        # Seal the tape with a done marker (replay consumers close on it)
        # and pop it after a grace window so late reattach still sees it.
        # The pop must be generation-aware: a NEW turn in the same session
        # may have installed a fresh tape within the grace window — popping
        # by session id alone would delete a live turn's tape mid-run.
        with _TURNS_LOCK:
            tape = _TURN_TAPES.get(session_id)
            if tape is not None:
                tape.append({"type": "done", "content": None})

        def _pop_tape_if_current(_t=tape):
            with _TURNS_LOCK:
                if _TURN_TAPES.get(session_id) is _t:
                    _TURN_TAPES.pop(session_id, None)

        seal = threading.Timer(_TAPE_GRACE_S, _pop_tape_if_current)
        seal.daemon = True
        seal.start()
        with _TURNS_LOCK:
            events = _ACTIVE_TURNS.get(session_id)
            if events is not None:
                events.discard(abort_event)
                if not events:
                    _ACTIVE_TURNS.pop(session_id, None)
        # Deregistered first: the after-turn hooks must see this turn as gone
        # (a job finishing now wakes the session instead of queueing behind it).
        threading.Thread(
            target=_after_turn, args=(session_id, abort_event.is_set()), daemon=True
        ).start()


# The job table wakes idle sessions through the same host turn (spec 裁决 20).
jobs.bind(
    is_busy=lambda sid: bool(_ACTIVE_TURNS.get(sid)),
    wake=host_turn,
)


def _free_port(preferred: int | None) -> int:
    port = preferred or 0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))
        return sock.getsockname()[1]


def run_server(
    port: int | None = None, runtime: WebUIRuntime | None = None, hub_port: int | None = None
) -> None:
    import webbrowser  # noqa: PLC0415 (only needed to open the browser)

    from pot.hub.app import Hub  # noqa: PLC0415 (lazy: console mode never pays for it)

    rt = runtime or WebUIRuntime()
    server = make_webui_server(port, rt)
    url = f"http://localhost:{server.server_address[1]}"
    # The launcher (spec §4 方案 A) spawns this process and parses these two
    # lines: WebUI for "open chat", hub for /api/board/* + /api/host/status.
    hub = Hub("pot", WEBUI_TOKEN, PROJECT_ROOT / "data", port=hub_port if hub_port else 0)
    hub.webui_url = url
    hub.start()
    print(f"  Pot WebUI: {url}", flush=True)
    print(f"  Pot Hub: http://127.0.0.1:{hub.port}", flush=True)
    print("  Press Ctrl+C to stop", flush=True)
    # The launcher owns "open chat" (its own button/tray); it sets
    # POT_NO_BROWSER=1 so spawning the host does not hijack the desktop.
    if not os.environ.get("POT_NO_BROWSER"):
        webbrowser.open(url)
    mcp_tools = rt.mcp_tools()
    if mcp_tools:
        print(f"  MCP: {len(mcp_tools)} tools loaded -> {', '.join(sorted(mcp_tools))}")
    elif load_config().mcp_servers:
        print("  MCP: servers configured but none loaded (see stderr)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hub.stop()
        server.server_close()


class WebUIServer(ThreadingHTTPServer):
    """Browsers open speculative connections and reset them constantly;
    those are noise, not errors — don't dump a traceback per reset."""

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(
            exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError)
        ):
            return
        super().handle_error(request, client_address)


def make_webui_server(port: int | None, runtime: WebUIRuntime) -> WebUIServer:
    """Build (not start) the WebUI server; tests embed this in-process."""
    _HOST["runtime"] = runtime  # host-driven turns (dispatch, job wakeups) target it
    handler = type("BoundHandler", (YesSirHandler,), {"runtime": runtime})
    server = WebUIServer(("127.0.0.1", _free_port(port)), handler)
    runlog.note("WebUI listening on 127.0.0.1:%d", server.server_address[1])
    return server
