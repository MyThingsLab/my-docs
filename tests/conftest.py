from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from mythings.engine import EngineRequest, EngineResult

# Shared fakes come from mythings.testing (plain imports; aliased fixture
# re-export + getfixturevalue wrapper per core docs/CONVENTIONS.md).
from mythings.testing import FakeGh, GitRepo, make_git_repo
from mythings.testing import clean_git_env as _shared_clean_git_env  # noqa: F401


@pytest.fixture(autouse=True)
def _clean_git_env(request: pytest.FixtureRequest) -> None:
    # Real git worktrees in every test; hook-launched pytest (pre-commit)
    # must not leak GIT_* into them.
    request.getfixturevalue("_shared_clean_git_env")


class ScriptedEngine:
    # Not the shared one: my-docs makes one Engine call per stale tool, so this
    # double replies per tool name from request.context — a shape no other
    # tool needs.
    def __init__(self, replies: str | dict[str, str]) -> None:
        # A single reply for every call, or a per-tool-name mapping.
        self.replies = replies
        self.calls: list[EngineRequest] = []

    def run(self, request: EngineRequest) -> EngineResult:
        self.calls.append(request)
        if isinstance(self.replies, str):
            return EngineResult(text=self.replies)
        tool = request.context.get("tool", "")
        return EngineResult(text=self.replies[tool])


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def fake_gh(
    *,
    org_repos: list[str] | None = None,
    files: dict[str, dict[str, str]] | None = None,
    existing_pr: dict | None = None,
) -> FakeGh:
    # files: {"MyThingsLab/<repo>": {"README.md": "...", "CLAUDE.md": "..."}}
    repo_files = files or {}

    def api(argv: list[str]) -> str:
        # argv: ["api", "repos/<owner>/<repo>/contents/<path>", "--jq", ".content"]
        path_arg = argv[1]
        prefix = "repos/"
        assert path_arg.startswith(prefix)
        owner, repo, _, file_path = path_arg[len(prefix) :].split("/", 3)
        slug = f"{owner}/{repo}"
        if file_path not in repo_files.get(slug, {}):
            raise AssertionError(f"missing file (simulated 404): {slug}/{file_path}")
        return _b64(repo_files[slug][file_path])

    return FakeGh(
        {
            ("repo", "list"): json.dumps([{"name": n} for n in (org_repos or [])]),
            ("api",): api,
            ("pr", "list"): json.dumps([existing_pr] if existing_pr else []),
            ("pr", "create"): "https://github.com/MyThingsLab/mythingslab.github.io/pull/7\n",
        }
    )


def make_docs_site(tmp_path: Path) -> Path:
    repo = make_git_repo(tmp_path, files={"README.md": "# mythingslab.github.io\n"}).path
    (repo / "_tools").mkdir()
    return repo


def branch_file(repo: Path, branch: str, path: str) -> str:
    return GitRepo(path=repo, origin=repo.parent / "origin.git").read_committed(branch, path)
