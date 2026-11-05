"""Concurrent claim stress (spec §8 M1 acceptance, §10-5): WAL + single-writer transaction."""

import sqlite3
import threading

from pot.board import Board
from pot.errors import PotError
from pot.roles import Actor


def test_wal_mode_enabled(repo, tmp_path):
    """spec 裁决 16 / 风险 5：看板库必须是 WAL（压测定参）。"""
    db = tmp_path / "wal.sqlite"
    Board(db, repo)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()


def test_concurrent_claim_single_winner(repo, board):
    """8 线程抢 40 张卡：每张恰好一次成功，无双 holder。"""
    repo.create({"id": "r1", "wip": 100}, creator="human")
    cards = [board.human_create(title=f"c{i}") for i in range(40)]
    lock = threading.Lock()
    successes = {c["id"]: 0 for c in cards}
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        for c in cards:
            try:
                fresh = board.get(c["id"])
                board.claim(Actor("r1", f"s{threading.get_ident()}"), c["id"], fresh["ifVersion"])
            except PotError:
                continue  # stale_version / already_held：输家路径
            with lock:
                successes[c["id"]] += 1

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(n == 1 for n in successes.values()), successes
    for c in cards:
        assert board.get(c["id"])["holder"] is not None


def test_concurrent_wip_respected(repo, board):
    """裁决 33: wip 按实例计——8 线程共抢同一个实例（wip=2）：成功恰好 2 次。"""
    repo.create({"id": "r1", "wip": 2}, creator="human")
    cards = [board.human_create(title=f"c{i}") for i in range(20)]
    lock = threading.Lock()
    successes = []
    barrier = threading.Barrier(8)
    instance = Actor("r1", "shared-instance")  # every thread plays ONE instance

    def worker():
        barrier.wait()
        for c in cards:
            try:
                fresh = board.get(c["id"])
                board.claim(instance, c["id"], fresh["ifVersion"])
            except PotError:
                continue
            with lock:
                successes.append(c["id"])

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # The same instance may re-touch cards it already holds (holder re-claim =
    # renew, by design) — the WIP gate is about how many DISTINCT cards it holds.
    assert len(set(successes)) == 2, successes
    held = [c for c in cards if board.get(c["id"])["holder"] is not None]
    assert len(held) == 2


def test_concurrent_create_unique_ids(repo, board):
    """并发建卡：id 不撞。"""
    repo.create({"id": "r1", "canCreateCard": True}, creator="human")
    lock = threading.Lock()
    ids = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        for i in range(10):
            card = board.create(Actor("r1", f"s{threading.get_ident()}"), title=f"x{i}")
            with lock:
                ids.append(card["id"])

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(ids) == 80
    assert len(set(ids)) == 80
