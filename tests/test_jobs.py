"""Job table (spec §3.4 裁决 20): bash detach, monitor finalize, busy-queue
flush, idle wake, manual kill — no network, real cmd.exe processes."""

from __future__ import annotations

import re
import time

import pytest

from pot import jobs
from pot.tools.shell import tool_bash


@pytest.fixture(autouse=True)
def _clean_bindings():
    """Save the host bindings (installed by pot.server), run bare, restore.

    Teardown kills every still-running job BEFORE restoring: a job finalizing
    after restore would wake the real host_turn — that leak once created two
    real sessions and burned two real LLM turns in data/sessions
    (2026-11-04). killed/interrupted jobs never wake, so the order is safe.
    """
    saved = dict(jobs._BINDINGS)
    jobs._BINDINGS.clear()
    jobs.set_current_session(None)
    yield
    for job in list(jobs._JOBS.values()):
        if job.status == "running":
            jobs.kill(job.id)
    jobs._JOBS.clear()
    jobs._PENDING.clear()
    jobs._BINDINGS.clear()
    jobs._BINDINGS.update(saved)
    jobs.set_current_session(None)


def _wait_for(predicate, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("condition not met in time")


def _detach(session_id: str, command: str) -> str:
    jobs.set_current_session(session_id)
    out = tool_bash(command, should_detach=lambda: True)
    assert out.startswith("BACKGROUNDED (job="), out
    return re.search(r"job=([0-9a-f]+)", out).group(1)


def test_detach_hands_the_live_process_to_the_job_table():
    jid = _detach("s1", "ping -n 3 127.0.0.1")
    job = jobs.get(jid)
    assert job is not None
    assert job.session_id == "s1" and job.status == "running" and job.pid > 0
    # the monitor owns it now: finalize on natural exit, no kill, no re-run
    _wait_for(lambda: jobs.get(jid).status != "running")
    job = jobs.get(jid)
    assert job.status == "done" and job.exit_code == 0
    assert "Ping" in job.result  # output captured from the detached process
    assert jobs.list_jobs("s1")[0]["id"] == jid


def test_finished_job_wakes_an_idle_session_with_the_report():
    wakes: list[tuple[str, str]] = []
    jobs.bind(is_busy=lambda _sid: False, wake=lambda sid, msg: wakes.append((sid, msg)))
    jid = _detach("s2", "ping -n 3 127.0.0.1")
    _wait_for(lambda: wakes)
    sid, msg = wakes[0]
    assert sid == "s2"
    assert "[job report]" in msg and jid in msg and "Ping" in msg


def test_finished_job_queues_while_the_session_is_busy_then_flush_delivers():
    wakes: list[tuple[str, str]] = []
    jobs.bind(is_busy=lambda _sid: True, wake=lambda sid, msg: wakes.append((sid, msg)))
    jid = _detach("s3", "ping -n 3 127.0.0.1")
    _wait_for(lambda: jobs.get(jid).status != "running")
    time.sleep(0.3)  # a wake would have raced in by now if it were going to
    assert wakes == []  # busy → queued, never woken mid-turn
    pending = jobs.flush("s3")
    assert [j.id for j in pending] == [jid]
    assert "[job report]" in jobs.report(pending[0])
    assert jobs.flush("s3") == []  # drained exactly once


def test_manual_kill_finalizes_as_killed_and_never_wakes():
    wakes: list[tuple[str, str]] = []
    jobs.bind(is_busy=lambda _sid: False, wake=lambda sid, msg: wakes.append((sid, msg)))
    jid = _detach("s4", "ping -n 30 127.0.0.1")
    assert jobs.kill(jid) is True
    _wait_for(lambda: jobs.get(jid).status != "running")
    assert jobs.get(jid).status == "killed"
    assert jobs.kill(jid) is False  # already finalized
    time.sleep(0.3)
    assert wakes == []  # a user-cancelled job is not news


def test_job_without_a_session_is_tracked_but_never_delivered():
    wakes: list[tuple[str, str]] = []
    jobs.bind(is_busy=lambda _sid: False, wake=lambda sid, msg: wakes.append((sid, msg)))
    jid = _detach("", "ping -n 3 127.0.0.1")
    _wait_for(lambda: jobs.get(jid).status != "running")
    assert jobs.get(jid).session_id == ""
    assert wakes == []
    assert jobs.flush("") == []


def test_list_jobs_filters_by_session():
    a = _detach("sA", "ping -n 3 127.0.0.1")
    b = _detach("sB", "ping -n 3 127.0.0.1")
    assert {j["id"] for j in jobs.list_jobs("sA")} == {a}
    assert {j["id"] for j in jobs.list_jobs("sB")} == {b}
    assert {j["id"] for j in jobs.list_jobs()} >= {a, b}
