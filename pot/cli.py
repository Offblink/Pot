"""Console single-shot mode: `python -m pot "question"`."""

from pot import dispatch
from pot.agents import build_planner
from pot.config import load_config
from pot.events import ConsoleSink


def run_single_shot(query: str) -> int:
    cfg = load_config()
    if not cfg.configured:
        print("ERROR: API key not configured. Edit config.json (GUI: 设置 page).")
        return 1
    sink = ConsoleSink()
    agent = build_planner(cfg, sink, board=dispatch.board())
    messages = [{"role": "user", "content": query}]
    print()
    agent.run(messages)
    print()
    return 0
