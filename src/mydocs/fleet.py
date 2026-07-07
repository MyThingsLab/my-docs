from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from mythings.github import Runner, _gh
from mythings.ledger import Ledger

ORG = "MyThingsLab"

# Repos that are part of the fleet but not a per-tool docs page: the docs site
# itself, and any repo whose page (if it ever gets one) is out of scope for
# this per-tool loop (see design doc's "Non-tool pages" open question).
_EXCLUDED = {"mythingslab.github.io"}


@dataclass(frozen=True)
class ToolRepo:
    name: str
    slug: str  # "MyThingsLab/<name>"


@dataclass(frozen=True)
class ToolDocs:
    repo: ToolRepo
    readme: str
    claude_md: str

    @property
    def readme_hash(self) -> str:
        return _hash(self.readme)

    @property
    def claude_md_hash(self) -> str:
        return _hash(self.claude_md)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def list_org_repos(*, runner: Runner = _gh) -> list[str]:
    raw = runner(["repo", "list", ORG, "--json", "name", "--limit", "200"])
    return [obj["name"] for obj in json.loads(raw)]


def _file_or_none(repo: ToolRepo, path: str, *, runner: Runner) -> str | None:
    try:
        return runner(
            ["api", f"repos/{repo.slug}/contents/{path}", "--jq", ".content"]
        )
    except Exception:  # noqa: BLE001 - degrade to "no file", not a hard failure
        return None


def _decode_b64(content: str | None) -> str:
    if not content:
        return ""
    return base64.b64decode(content.replace("\n", "")).decode("utf-8")


def has_claude_md(name: str, *, runner: Runner = _gh) -> bool:
    repo = ToolRepo(name=name, slug=f"{ORG}/{name}")
    return _file_or_none(repo, "CLAUDE.md", runner=runner) is not None


def candidate_tools(
    names: list[str] | None = None, *, runner: Runner = _gh
) -> list[ToolRepo]:
    if names is None:
        names = [n for n in list_org_repos(runner=runner) if n not in _EXCLUDED]
    else:
        names = [n for n in names if n not in _EXCLUDED]
    return [
        ToolRepo(name=n, slug=f"{ORG}/{n}")
        for n in names
        if has_claude_md(n, runner=runner)
    ]


def fetch_docs(repo: ToolRepo, *, runner: Runner = _gh) -> ToolDocs:
    readme = _decode_b64(_file_or_none(repo, "README.md", runner=runner))
    claude_md = _decode_b64(_file_or_none(repo, "CLAUDE.md", runner=runner))
    return ToolDocs(repo=repo, readme=readme, claude_md=claude_md)


def last_sync_hashes(ledger: Ledger, tool_name: str) -> tuple[str, str] | None:
    entries = [
        e
        for e in ledger.read(tool="mydocs", kind="docs_sync")
        if e.data.get("repo") == f"{ORG}/{tool_name}" and e.outcome == "success"
    ]
    if not entries:
        return None
    latest = max(entries, key=lambda e: e.ts)
    readme_hash = latest.data.get("readme_hash")
    claude_md_hash = latest.data.get("claude_md_hash")
    if readme_hash is None or claude_md_hash is None:
        return None
    return readme_hash, claude_md_hash


def is_stale(docs: ToolDocs, ledger: Ledger) -> bool:
    last = last_sync_hashes(ledger, docs.repo.name)
    if last is None:
        return True
    return (docs.readme_hash, docs.claude_md_hash) != last


def stale_tools(
    tools: list[ToolRepo],
    ledger: Ledger,
    *,
    runner: Runner = _gh,
    fetch: Callable[[ToolRepo], ToolDocs] | None = None,
) -> list[ToolDocs]:
    fetcher = fetch or (lambda repo: fetch_docs(repo, runner=runner))
    all_docs = [fetcher(repo) for repo in tools]
    return [docs for docs in all_docs if is_stale(docs, ledger)]
