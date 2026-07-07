from __future__ import annotations

import argparse
from pathlib import Path

from mythings.engine import ClaudeCLIEngine, Engine, NoopEngine
from mythings.ledger import Ledger

from mydocs.docsync import DEFAULT_SITE, DocSync, Result


def build_engine(name: str, *, model: str | None = None) -> Engine:
    if name == "claude-cli":
        return ClaudeCLIEngine(model=model)
    return NoopEngine()


def _render(result: Result) -> str:
    line = f"{result.outcome}: {result.detail}"
    if result.pr is not None:
        line += f" — PR #{result.pr}"
    for tool in result.tools:
        line += f"\n  {tool.outcome}: {tool.tool}"
        if tool.path and tool.outcome == "success":
            line += f" [{tool.path}]"
    return line


def _make(args: argparse.Namespace) -> DocSync:
    return DocSync(
        repo_root=args.repo_root,
        repo=args.repo,
        ledger=Ledger(args.ledger),
        base=args.base,
        engine=build_engine(args.engine, model=args.engine_model),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mydocs",
        description="Keeps the fleet's docs site in sync with each tool's README/CLAUDE.md.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sync = sub.add_parser("sync", help="sync stale tool docs pages into one PR")
    sync.add_argument("--repos", help="comma-separated tool repo names (default: --all)")
    sync.add_argument(
        "--all", action="store_true", help="enumerate every MyThingsLab repo with a CLAUDE.md"
    )
    sync.add_argument(
        "--repo", default=DEFAULT_SITE, help=f"docs-site slug owner/name (default: {DEFAULT_SITE})"
    )
    sync.add_argument("--repo-root", type=Path, default=Path.cwd(), help="local docs-site clone")
    sync.add_argument("--base", default="main", help="base branch for the PR")
    sync.add_argument("--ledger", type=Path, default=Path(".mythings/ledger.jsonl"))
    sync.add_argument("--no-pr", action="store_true", help="skip opening the docs-sync PR")
    sync.add_argument(
        "--engine",
        choices=("noop", "claude-cli"),
        default="noop",
        help="Engine backend for page rendering (default: noop — copies the README verbatim)",
    )
    sync.add_argument("--engine-model", help="model for --engine claude-cli")

    args = parser.parse_args(argv)

    if args.cmd == "sync":
        if not args.repos and not args.all:
            parser.error("sync requires --repos or --all")
        repos = (
            [r.strip() for r in args.repos.split(",") if r.strip()] if args.repos else None
        )
        docsync = _make(args)
        result = docsync.sync(repos=repos, no_pr=args.no_pr)
    else:
        raise AssertionError(f"unreachable cmd: {args.cmd}")

    print(_render(result))
    return 1 if result.outcome == "failure" else 0


if __name__ == "__main__":
    raise SystemExit(main())
