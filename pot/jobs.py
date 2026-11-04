"""后台作业表 (spec §3.4 裁决 20): no-kill detach, cross-turn survival, idle wake.

A 后台执行 press stops only the WAITING: `tool_bash` hands its live process and
open output handles to this table and returns at once — the command is neither
killed nor re-dispatched. The job outlives the turn that started it. When the
process exits the result is delivered: the session is woken with it if idle, or
the report queues for the turn's end if a turn is running (挂起补投).

Boundaries: the host exiting finalizes every running job (kill + record); a
manual kill does the same on request.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pot import runlog

RESULT_CAP = 20_000  # chars of output carried into the wake message


@dataclass
class Job:
    id: str
    session_id: str
    command: str
    cwd: str | None
    pid: int
    bat: Path
    out_fd: int
    err_fd: int
    started: float
    status: str = "running"  # running | done | failed | killed | interrupted
    exit_code: int | None = None
    result: str = ""
    finished: float | None = None
    # The process object lives in the monitor thread's closure; kill() reaches
    # it through this box so the dataclass stays JSON-shape for list routes.
    proc: subprocess.Popen | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sessionId": self.session_id,
            "command": self.command,
            "status": self.status,
            "exitCode": self.exit_code,
            "started": self.started,
            "finished": self.finished,
        }


_LOCK = threading.Lock()
_JOBS: dict[str, Job] = {}
# Finished jobs whose session had a turn running: delivered at that turn's end.
_PENDING: dict[str, list[Job]] = {}
# Bindings server.py installs (dict-mutated, never rebound): "is a turn running
# in this session" and "run a host-side turn with this message".
_BINDINGS: dict = {}

# The session whose turn is executing on THIS thread (tool calls run inline in
# the agent loop, so a thread-local is exactly the turn's identity).
_CURRENT = threading.local()


def current_session() -> str:
    return getattr(_CURRENT, "sid", "") or ""


def set_current_session(session_id: str | None) -> None:
    _CURRENT.sid = session_id or ""


def bind(*, is_busy: Callable[[str], bool], wake: Callable[[str, str], None]) -> None:
    """server.py installs the host hooks once at import."""
    _BINDINGS["is_busy"] = is_busy
    _BINDINGS["wake"] = wake


def adopt(
    *,
    command: str,
    cwd: str | None,
    bat: Path,
    out_fd: int,
    err_fd: int,
    proc: subprocess.Popen,
) -> str:
    """Take ownership of a detached bash run: monitor it, then deliver."""
    job = Job(
        id=uuid.uuid4().hex[:8],
        session_id=current_session(),
        command=command,
        cwd=cwd,
        pid=proc.pid,
        bat=bat,
        out_fd=out_fd,
        err_fd=err_fd,
        started=time.time(),
        proc=proc,
    )
    with _LOCK:
        _JOBS[job.id] = job
    threading.Thread(target=_monitor, args=(job,), daemon=True, name=f"job-{job.id}").start()
    runlog.note("job %s detached (pid=%s, session=%s)", job.id, proc.pid, job.session_id or "-")
    return job.id


def _read_fd(fd: int) -> str:
    """Everything written so far; closes the handle (O_TEMPORARY then retires
    the file once the child's inherited handles are gone too)."""
    chunks: list[bytes] = []
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            chunks.append(block)
    except OSError:
        pass
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _monitor(job: Job) -> None:
    proc = job.proc
    code = -1
    if proc is not None:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            code = proc.wait()
    out = _read_fd(job.out_fd)
    err = _read_fd(job.err_fd)
    with contextlib.suppress(OSError):
        job.bat.unlink(missing_ok=True)
    result = out
    if err:
        result += ("\n[stderr]\n" if result else "") + err
    if not result.strip():
        result = "(no output)"
    if code not in (0, None):
        result += f"\n[exit: {code}]"
    with _LOCK:
        job.exit_code = code
        job.result = result[:RESULT_CAP]
        job.finished = time.time()
        if job.status == "running":  # kill()/finalize_all() may have set it first
            job.status = "done" if code == 0 else "failed"
        status = job.status
    runlog.note("job %s finished: %s (exit=%s)", job.id, status, code)
    _deliver(job)


def _deliver(job: Job) -> None:
    """Idle session → wake it with the report; busy → queue for turn end.
    A manually killed / interrupted job finalizes its record only — the user
    already knows, a wake turn would be noise."""
    if not job.session_id or job.status in ("killed", "interrupted"):
        return
    with _LOCK:
        is_busy = _BINDINGS.get("is_busy")
        if is_busy is not None and is_busy(job.session_id):
            _PENDING.setdefault(job.session_id, []).append(job)
            return
        waker = _BINDINGS.get("wake")
    if waker is not None:
        # Wake on its own thread: the monitor must not become the turn runner.
        threading.Thread(
            target=_run_wake, args=(waker, job), daemon=True, name=f"job-wake-{job.id}"
        ).start()


def _run_wake(waker: Callable[[str, str], None], job: Job) -> None:
    with contextlib.suppress(Exception):  # a crashed wake must not kill the monitor
        waker(job.session_id, report(job))


def report(job: Job) -> str:
    return (
        "[job report] A background job you moved to the background has FINISHED."
        " This is its final output; the user sees your reply, not this note.\n"
        f"- id={job.id} status={job.status} exit={job.exit_code}\n"
        f"  command: {job.command}\n"
        f"  output:\n{job.result}"
    )


def flush(session_id: str) -> list[Job]:
    """Jobs that finished while the session was busy: called at turn end."""
    with _LOCK:
        return list(_PENDING.pop(session_id, []))


def list_jobs(session_id: str | None = None) -> list[dict]:
    with _LOCK:
        jobs = [j for j in _JOBS.values() if session_id in (None, "", j.session_id)]
    return sorted((j.to_dict() for j in jobs), key=lambda d: d["started"], reverse=True)


def get(job_id: str) -> Job | None:
    with _LOCK:
        return _JOBS.get(job_id)


def kill(job_id: str) -> bool:
    """Manual kill (spec: 手动 kill is a job boundary): claim the status FIRST
    — the monitor's wait() returns the moment the tree dies and would record
    `failed` before taskkill ever came back — then tree-kill; the monitor
    keeps `killed` and only fills the exit/result fields."""
    job = get(job_id)
    if job is None:
        return False
    with _LOCK:
        if job.status != "running":
            return False
        job.status = "killed"
    _kill_tree(job)
    return True


def _kill_tree(job: Job) -> None:
    proc = job.proc
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
                timeout=10,
            )
        else:
            os.killpg(os.getpgid(proc.pid), 15)
    except (OSError, subprocess.SubprocessError):
        pass
    with _LOCK:
        if job.status == "running":
            job.status = "killed"  # the monitor's wait() returns; it must not overwrite


def _finalize_all() -> None:
    """Host exit finalizes every running job (spec: 退出即定稿). Status is
    claimed before the kill for the same reason as kill(): the monitor's
    wait() races back the moment the tree dies."""
    with _LOCK:
        running = [j for j in _JOBS.values() if j.status == "running"]
        for job in running:
            job.status = "interrupted"
    for job in running:
        _kill_tree(job)
        runlog.note("job %s interrupted by host exit", job.id)


atexit.register(_finalize_all)
