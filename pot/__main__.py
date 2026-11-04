"""Entry point.

Single-host only (spec §1.2 — rooms/mobile/GUI are gone; the CMP launcher comes
in milestone M4):

    python -m pot [query]           console single-shot
    python -m pot --web [--port P]  WebUI server (browser opens)
"""

import argparse
import sys

from pot import runlog
from pot.config import local_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pot",
        description="Pot — single-host agent harness with resident roles and a task board",
    )
    parser.add_argument("query", nargs="*", help="single-shot query (console mode)")
    parser.add_argument("--version", action="version", version=f"pot {local_version()}")
    parser.add_argument("--web", action="store_true", help="single-host WebUI server mode")
    parser.add_argument("--port", type=int, help="WebUI port (--web)")
    return parser


def main(argv: list[str] | None = None) -> int:
    runlog.setup()  # what a bug report gets attached to (logs/ beside config.json)
    args = build_parser().parse_args(argv)
    runlog.environment(_mode(args), sys.argv)
    if args.query:
        from pot.cli import run_single_shot  # noqa: PLC0415 (lazy: keep --help dependency-free)

        return run_single_shot(" ".join(args.query))
    if args.web:
        from pot.server import run_server  # noqa: PLC0415

        run_server(args.port)
        return 0
    build_parser().print_help()
    return 0


def _mode(args: argparse.Namespace) -> str:
    """Which entry the log's banner is for: the first one that fits."""
    if args.web:
        return "web"
    return "cli" if args.query else "help"


if __name__ == "__main__":
    raise SystemExit(main())
