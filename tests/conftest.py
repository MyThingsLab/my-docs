from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import pytest
from mythings.engine import EngineRequest, EngineResult


@pytest.fixture(autouse=True)
def _clean_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # pre-commit runs hooks with GIT_DIR/GIT_INDEX_FILE set; they leak into the
    # git subprocesses these tests spawn (and into isolation.Workspace) and break
    # worktree ops on the throwaway repo. Real runs are not inside a hook.
    for var in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_OBJECT_DIRECTORY"):
        monkeypatch.delenv(var, raising=False)


class ScriptedEngine:
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


class SpyEngine:
    def __init__(self) -> None:
        self.calls: list[EngineRequest] = []

    def run(self, request: EngineRequest) -> EngineResult:
        self.calls.append(request)
        return EngineResult(text="")


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class FakeRunner:
    # Mocks only the `gh` subprocess boundary.
    def __init__(
        self,
        *,
        org_repos: list[str] | None = None,
        files: dict[str, dict[str, str]] | None = None,
        existing_pr: dict | None = None,
    ) -> None:
        self.calls: list[list[str]] = []
        self.org_repos = org_repos or []
        # files: {"MyThingsLab/<repo>": {"README.md": "...", "CLAUDE.md": "..."}}
        self.files = files or {}
        self.existing_pr = existing_pr

    def __call__(self, argv: list[str]) -> str:
        self.calls.append(argv)
        if argv[:2] == ["repo", "list"]:
            return json.dumps([{"name": n} for n in self.org_repos])
        if argv[:2] == ["api"] or argv[0] == "api":
            return self._api(argv)
        if argv[:2] == ["pr", "list"]:
            return json.dumps([self.existing_pr] if self.existing_pr else [])
        if argv[:2] == ["pr", "create"]:
            return "https://github.com/MyThingsLab/mythingslab.github.io/pull/7\n"
        raise AssertionError(f"unexpected gh call: {argv}")

    def _api(self, argv: list[str]) -> str:
        # argv: ["api", "repos/<owner>/<repo>/contents/<path>", "--jq", ".content"]
        path_arg = argv[1]
        prefix = "repos/"
        assert path_arg.startswith(prefix)
        rest = path_arg[len(prefix) :]
        owner, repo, _, file_path = rest.split("/", 3)
        slug = f"{owner}/{repo}"
        repo_files = self.files.get(slug, {})
        if file_path not in repo_files:
            raise AssertionError(f"missing file (simulated 404): {slug}/{file_path}")
        return _b64(repo_files[file_path])


def make_docs_site(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    repo = tmp_path / "site"
    repo.mkdir()
    (repo / "_tools").mkdir()
    (repo / "README.md").write_text("# mythingslab.github.io\n", encoding="utf-8")

    def _git(*argv: str) -> None:
        subprocess.run(["git", "-C", str(repo), *argv], check=True, capture_output=True, text=True)

    _git("init", "-b", "main")
    _git("config", "user.email", "t@example.com")
    _git("config", "user.name", "MyDocs")
    _git("add", "-A")
    _git("commit", "-m", "init")
    _git("remote", "add", "origin", str(origin))
    _git("push", "-u", "origin", "main")
    return repo


def branch_file(repo: Path, branch: str, path: str) -> str:
    origin = repo.parent / "origin.git"
    proc = subprocess.run(
        ["git", "-C", str(origin), "show", f"{branch}:{path}"],
        capture_output=True,
        text=True,
    )
    return proc.stdout
