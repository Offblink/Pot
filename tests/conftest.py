import pytest

from pot.board import Board
from pot.roles import RoleRepo


@pytest.fixture()
def repo(tmp_path):
    return RoleRepo(tmp_path / "roles")


@pytest.fixture()
def board(tmp_path, repo):
    return Board(tmp_path / "board.sqlite", repo)
