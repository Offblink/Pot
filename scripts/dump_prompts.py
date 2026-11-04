"""Print the exact system prompts the host assembles: Planner and a role.

Run: python scripts/dump_prompts.py

Pot is single-host (spec §1.2): user sessions build the Planner, sessions
carrying a `role` key build that resident role. This builds the same agents
the host builds and prints both prompts, with a per-section size table so a
prompt that grew or lost a section is visible.

The section table is checked, not rebuilt: each known piece is looked up in the
assembled prompt, and a piece reported MISSING means an assembly site moved and
this script needs the matching change.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # runnable from anywhere

# E402 is not raised after a sys.path edit, so these carry no noqa.
from pot import dispatch, skills
from pot.agent import SYSTEM_PROMPT
from pot.agents import PLANNER_ADDENDUM, ROLE_SECTION, build_planner, build_role
from pot.config import load_config
from pot.diary import section as diary_section
from pot.events import NullSink
from pot.roles import Role


def _table(label: str, prompt: str, pieces: list[tuple[str, str]]) -> None:
    print(f"{label}: {len(prompt)} chars, {prompt.count(chr(10)) + 1} lines")
    for piece_label, text in pieces:
        if not text:
            continue
        at = prompt.find(text)
        where = f"offset {at}" if at >= 0 else "MISSING (assembly changed?)"
        print(f"  {len(text):>6} chars  {piece_label:<22} {where}")
    print("-" * 72)


def main() -> int:
    cfg = load_config()
    board = dispatch.board()
    planner = build_planner(cfg, NullSink(), board=board).system_prompt
    role = build_role(
        cfg,
        NullSink(),
        role=Role(id="sample", name="Sample", mission="Do the thing.", tools=["shell"]),
        session_id="sample-session",
        board=board,
    ).system_prompt

    planner_pieces = [
        ("base SYSTEM_PROMPT", SYSTEM_PROMPT),
        ("planner addendum", PLANNER_ADDENDUM),
        ("skills section", skills.section()),
    ]
    if cfg.diary:
        planner_pieces.append(("diary section", diary_section()))
    _table("planner", planner, planner_pieces)
    _table(
        "role",
        role,
        [
            ("base SYSTEM_PROMPT", SYSTEM_PROMPT),
            ("mission line", "## Mission (Sample)"),
            ("role section", ROLE_SECTION),
            ("skills section", skills.section()),
        ],
    )
    print("=" * 72)
    print(planner)
    print("=" * 72)
    print(role)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
