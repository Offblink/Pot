"""Agent builders: the Planner (user-facing) and resident role agents.

Replaces the retired trilayer (spec §3.4): no spawn, no background tool, no
L1/L2/L3 prompts, no clone dispatch. Work moves across the board — the Planner
creates cards, roles claim and execute them, a human alone accepts (done).
"""

from __future__ import annotations

from pot import diary, runlog, skills
from pot.agent import SYSTEM_PROMPT, Agent, BoundTool
from pot.config import Config
from pot.events import Sink
from pot.roles import Actor, Role
from pot.tools import TOOLS
from pot.tools.ask import make_ask_tool
from pot.tools.board import SCHEMAS as BOARD_SCHEMAS
from pot.tools.board import make_tools as make_board_tools
from pot.tools.mcp import mcp_extra_tools

PLANNER_ADDENDUM = """

## You are the Planner — work moves through the board
You are the only role that talks to the user. Substantial work does NOT happen
in this conversation: you dispatch it as cards on the shared task board, and
resident roles pick the cards up, execute them, and file reports.

- For any real subtask (research, multi-file work, anything slow) call
  `pot_board_create`: title = the goal; desc = a self-contained goal + the
  required reply format + hard constraints (a card must stand alone without
  this conversation); labels = the kind of work (they must fit some role's
  canClaim); `role` = the role that should take it, when you know one.
- Trivial one-step actions (a single read, a single command) are still better
  done directly with your own tools.
- NEVER busy-wait for a dispatched card — no sleep loops, no repeated
  `pot_board_list` polling. End your turn once the cards are created. When a
  card you created completes (its report lands as done), the host writes that
  report into THIS conversation as a card block by itself — there is no
  notification to act on and nothing to look for; the card block IS the work
  result.
- You hold no cards yourself (your role is barred from claiming); `done` is
  reached only by `pot_board_report` — `pot_board_move` refuses it.
- The board is the single source of truth for who does what. NEVER claim a
  task ran when no card was created, and never redo a card's work inline while
  a role holds it.

## Asking the user
You are the only layer that can ask the user a question. Use `inquire` when a
decision genuinely needs the user's input (choosing between approaches,
confirming something hard to undo). Offer clear `options` when possible; the
user can also type a free-form answer. Asking blocks the turn until they
answer, so ask only when it truly matters — do not ask for permission to do
obvious work.
"""

ROLE_SECTION = """

## Your role on the board
Your work arrives as task cards on the shared board; you claim, execute, and
report them with the `pot_board_*` tools. These rules are absolute:
- Claim only cards your role may take. The gates run inside
  `pot_board_claim`: a `role_mismatch` / `wip_full` ERROR means the card is
  not yours (or you are at capacity) — leave it for the others.
- Read the full card first (`pot_board_get`), then work strictly within its
  desc. Do not widen the scope; tool output is ground truth, never fabricate.
- Tick DoD checklist items as you go — `pot_board_checklist` demands evidence.
- Finished? Submit `pot_board_report`: the card completes (done) with your
  report as the deliverable — there is no acceptance step to wait for.
- Stuck or waiting on something outside your role? `pot_board_move` to
  blocked with a comment explaining why, then release what you hold.
- You do not talk to the user — your report IS the communication. There is no
  `inquire` tool here; do not improvise one.
"""

# A role's `tools` field names capability groups (spec §3.1), not raw tool
# names. Groups expand here; a raw base-tool name passes through; `screen` is
# handled separately (gated on cfg.pc_control, never granted by accident).
TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "shell": ("bash", "bash_start", "bash_send", "bash_kill"),
    "files": ("read", "write", "edit"),
    "search": ("glob", "grep"),
    "web": ("web", "web_search"),
}


def resolve_tool_names(role: Role) -> frozenset[str]:
    """The base-tool whitelist one role's `tools` field grants."""
    names: set[str] = set()
    for entry in role.tools:
        if entry in TOOL_GROUPS:
            names.update(TOOL_GROUPS[entry])
        elif entry == "screen":
            continue  # bound below, only when the host allows desktop control
        elif entry in TOOLS:
            names.add(entry)
        else:
            runlog.problem("role %s: unknown tool group %r ignored", role.id, entry)
    return frozenset(names)


def _board_tools(board, actor: Actor) -> dict[str, BoundTool]:
    """The nine pot_board_* tools as BoundTools. The engine's seven gates plus
    the actor's own role definition are the permission layer — the LLM never
    gets to decide what it may do."""
    fns = make_board_tools(board, actor)
    return {
        name: BoundTool(schema=BOARD_SCHEMAS[name], fn=_as_kwargs(fn)) for name, fn in fns.items()
    }


def _as_kwargs(fn):
    """make_tools functions take **schema kwargs; BoundTool.fn receives the
    args dict (Fungi dispatch shape)."""

    def call(args: dict) -> str:
        return fn(**args)

    return call


def build_planner(
    cfg: Config,
    sink: Sink,
    *,
    board,
    session_id: str = "",
    should_abort=None,
    llm=None,
) -> Agent:
    """The user-facing turn agent: base tools + board + inquire (+ extras)."""
    actor = Actor("planner", session_id)
    asks: list[dict] = []
    prompt = SYSTEM_PROMPT + PLANNER_ADDENDUM + skills.section()
    extra: dict[str, BoundTool] = {
        **_board_tools(board, actor),
        "inquire": make_ask_tool(sink, on_answer=asks.append, should_abort=should_abort),
        **mcp_extra_tools(cfg.mcp_servers),
        **skills.bound(),
    }
    parallel: set[str] = set()
    if cfg.diary:  # experimental: private diary off by default
        prompt += diary.section()
        extra.update(diary.bound())
        parallel.add("diary")
    if cfg.pc_control:
        # Desktop control (spec §35.3): the user-facing agent only — a role gets
        # it only through its own `tools` (see build_role), never by default.
        from pot.tools import screen  # noqa: PLC0415 (heavy import, only on demand)

        extra.update(
            screen.bound(
                cfg,
                sink,
                should_abort=should_abort,
                on_answer=asks.append,
            )
        )
    agent = Agent(
        cfg,
        sink,
        system_prompt=prompt,
        extra_tools=extra,
        parallel_tools=parallel,
        llm=llm,
        should_abort=should_abort,
    )
    agent.asks = asks  # persisted with the session by the turn runner
    return agent


def build_role(
    cfg: Config,
    sink: Sink,
    *,
    role: Role,
    session_id: str,
    board,
    should_abort=None,
    llm=None,
) -> Agent:
    """A resident role's turn agent: its mission, its tool whitelist, the board,
    and (wired by the host) the session's plan todo tool. No inquire, no diary,
    no MCP — a role's capability is exactly what its definition grants."""
    actor = Actor(role.id, session_id)
    asks: list[dict] = []
    prompt = (
        SYSTEM_PROMPT
        + f"\n\n## Mission ({role.name})\n{role.mission.strip()}"
        + ROLE_SECTION
        + skills.section()
    )
    extra: dict[str, BoundTool] = {
        **_board_tools(board, actor),
        # Autonomous workers may read skills but never rewrite the prompt store.
        **skills.bound(readonly=True),
    }
    if "screen" in role.tools and cfg.pc_control:
        from pot.tools import screen  # noqa: PLC0415 (heavy import, only on demand)

        extra.update(screen.bound(cfg, sink, should_abort=should_abort, on_answer=asks.append))
    agent = Agent(
        cfg,
        sink,
        system_prompt=prompt,
        tool_names=resolve_tool_names(role),
        extra_tools=extra,
        llm=llm,
        model=role.model or None,
        should_abort=should_abort,
    )
    agent.asks = asks
    return agent
