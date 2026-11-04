"""Print the exact system prompt the L1 orchestrator receives on its next turn.

Run: python scripts/dump_prompts.py

Pot is single-host (spec §1.2): the only role is the L1 orchestrator the user
talks to. This builds the same TriLayer object the host builds and prints its
prompt, with a per-section size table so a prompt that grew a section is
visible.

The section table is checked, not rebuilt: each known piece is looked up in the
assembled prompt, and a piece reported MISSING means an assembly site moved and
this script needs the matching change.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # runnable from anywhere

# E402 is not raised after a sys.path edit, so these carry no noqa.
from pot import skills
from pot.agent import SYSTEM_PROMPT
from pot.config import load_config
from pot.diary import section as diary_section
from pot.events import NullSink
from pot.trilayer import L1_ADDENDUM, TriLayer


def main() -> int:
    cfg = load_config()
    prompt = TriLayer(cfg, NullSink()).build_orchestrator(NullSink()).system_prompt
    pieces = [
        ("base SYSTEM_PROMPT", SYSTEM_PROMPT),
        ("L1 addendum", L1_ADDENDUM),
        ("skills section", skills.section()),
    ]
    if cfg.diary:
        pieces.append(("diary section", diary_section()))

    print(f"l1: {len(prompt)} chars, {prompt.count(chr(10)) + 1} lines")
    for label, text in pieces:
        if not text:
            continue
        at = prompt.find(text)
        where = f"offset {at}" if at >= 0 else "MISSING (assembly changed?)"
        print(f"  {len(text):>6} chars  {label:<22} {where}")
    print("-" * 72)
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
