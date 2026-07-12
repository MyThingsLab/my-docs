from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from myguard import Guard
from mythings.engine import Engine, NoopEngine
from mythings.github import GitHub, PullRequest, Runner, _gh, _pr_number
from mythings.isolation import Workspace, in_github_actions
from mythings.ledger import Ledger
from mythings.policy import Action, Decision, Policy

from mydocs.fleet import ToolDocs, _decode_b64, candidate_tools, stale_tools
from mydocs.page import Page, render_page

LABEL = "my-docs"
DEFAULT_SITE = "MyThingsLab/mythingslab.github.io"
_STYLE_ANCHOR_PATH = "_tools/my-researcher.md"  # any existing page; degrades if absent


class PolicyDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolResult:
    tool: str
    outcome: str  # success | skipped
    detail: str
    path: str | None = None


@dataclass(frozen=True)
class Result:
    outcome: str  # success | skipped | failure
    pr: int | None
    detail: str
    tools: list[ToolResult] = field(default_factory=list)


class DocSync:
    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        repo: str = DEFAULT_SITE,
        ledger: Ledger,
        base: str = "main",
        engine: Engine | None = None,
        policy: Policy | None = None,
        runner: Runner = _gh,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.repo = repo
        self.ledger = ledger
        self.base = base
        self.engine: Engine = engine or NoopEngine()
        self.policy: Policy = policy or Guard()
        self.runner = runner
        self.github = GitHub(repo, runner=runner)

    def sync(
        self, *, repos: list[str] | None = None, no_pr: bool = False
    ) -> Result:
        tools = candidate_tools(repos, runner=self.runner)
        stale = stale_tools(tools, self.ledger, runner=self.runner)

        if not stale:
            detail = "no stale tool docs"
            self.ledger.record(
                tool="mydocs", kind="docs_sync", outcome="skipped", detail=detail
            )
            return Result("skipped", None, detail)

        style_anchor = self._style_anchor()
        pages: dict[str, tuple[ToolDocs, Page]] = {}
        for docs in stale:
            page = render_page(self.engine, docs, style_anchor)
            pages[docs.repo.name] = (docs, page)

        pr = None
        if not no_pr:
            try:
                pr = self._open_pr(pages)
            except PolicyDenied as denied:
                return self._fail(str(denied))

        tool_results = [
            self._record_tool(docs, page, pr.number if pr else None)
            for docs, page in pages.values()
        ]
        detail = f"synced {len(tool_results)} tool doc page(s)"
        return Result("success", pr.number if pr else None, detail, tool_results)

    # ---- pr / git ----------------------------------------------------------

    def _open_pr(self, pages: dict[str, tuple[ToolDocs, Page]]) -> PullRequest:
        branch = f"{LABEL}/sync"
        existing = self._existing_pr(branch)
        with Workspace(self.repo_root, self.base) as tree:
            if existing is None:
                self._git(tree, ["checkout", "-B", branch])
            else:
                # Build on top of the branch an already-open PR tracks,
                # rather than resetting to base -- a reset-and-recommit
                # would diverge from what's on the remote and force-push is
                # a hard DENY (myguard's no_force_push rule), so a plain
                # push must stay a fast-forward.
                self._git(tree, ["fetch", "origin", branch])
                self._git(tree, ["checkout", "-B", branch, f"origin/{branch}"])
            for docs, page in pages.values():
                target = tree / page.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(page.content, encoding="utf-8")
                self._git(tree, ["add", page.path])
                self._git(tree, ["commit", "-m", f"docs: sync {docs.repo.name} page"])
            if existing is None:
                self._git(tree, ["push", "-u", "origin", branch])
            else:
                self._git(tree, ["push", "origin", branch])
        if existing is not None:
            return existing
        names = ", ".join(sorted(pages))
        self._guard(f"gh pr create --head {branch} --base {self.base}")
        return self.github.open_pr(
            title="docs: sync fleet tool pages",
            body=f"Refreshes docs pages for: {names}.",
            base=self.base,
            head=branch,
        )

    def _existing_pr(self, branch: str) -> PullRequest | None:
        argv = ["pr", "list", "--head", branch, "--state", "open", "--json", "number,url"]
        argv += ["--repo", self.repo]
        rows = json.loads(self.runner(argv))
        if not rows:
            return None
        row = rows[0]
        return PullRequest(number=row.get("number") or _pr_number(row["url"]), url=row["url"])

    def _style_anchor(self) -> str:
        try:
            raw = self.runner(
                ["api", f"repos/{self.repo}/contents/{_STYLE_ANCHOR_PATH}", "--jq", ".content"]
            )
        except Exception:  # noqa: BLE001 - no existing page yet, degrade
            return ""
        return _decode_b64(raw)

    def _git(self, tree: Path, argv: list[str]) -> None:
        self._guard("git " + " ".join(argv))
        proc = subprocess.run(["git", "-C", str(tree), *argv], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(argv)} failed: {proc.stderr.strip()}")

    def _guard(self, command: str) -> None:
        result = self.policy.evaluate(Action(kind="bash", payload={"command": command}))
        if result.under(unattended=in_github_actions()) is not Decision.ALLOW:
            raise PolicyDenied(f"policy blocked: {command} ({result.reason or result.decision})")

    # ---- ledger / results ----------------------------------------------------

    def _record_tool(self, docs: ToolDocs, page: Page, pr: int | None) -> ToolResult:
        self.ledger.record(
            tool="mydocs",
            kind="docs_sync",
            outcome="success",
            detail=f"docs page for {docs.repo.name}",
            repo=docs.repo.slug,
            page_path=page.path,
            readme_hash=docs.readme_hash,
            claude_md_hash=docs.claude_md_hash,
            pr_url=f"https://github.com/{self.repo}/pull/{pr}" if pr else None,
        )
        return ToolResult(
            tool=docs.repo.name, outcome="success", detail=f"docs page for {docs.repo.name}",
            path=page.path,
        )

    def _fail(self, detail: str) -> Result:
        self.ledger.record(tool="mydocs", kind="docs_sync", outcome="failure", detail=detail)
        return Result("failure", None, detail)
