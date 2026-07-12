from __future__ import annotations

from pathlib import Path

from mythings.ledger import Ledger

from conftest import fake_gh
from mydocs.fleet import ToolDocs, ToolRepo, candidate_tools, is_stale, stale_tools


def test_candidate_tools_excludes_docs_site_and_repos_without_claude_md() -> None:
    fake = fake_gh(
        org_repos=["my-guard", "no-claude-md-repo", "mythingslab.github.io"],
        files={
            "MyThingsLab/my-guard": {"README.md": "# my-guard\n", "CLAUDE.md": "# guard\n"},
            # no-claude-md-repo has no CLAUDE.md entry -> _file_or_none returns None
        },
    )

    tools = candidate_tools(runner=fake)

    assert [t.name for t in tools] == ["my-guard"]


def test_candidate_tools_respects_explicit_repos_list() -> None:
    fake = fake_gh(
        files={
            "MyThingsLab/my-guard": {"README.md": "# my-guard\n", "CLAUDE.md": "# guard\n"},
            "MyThingsLab/my-reporter": {"README.md": "# my-reporter\n", "CLAUDE.md": "# rep\n"},
        }
    )

    tools = candidate_tools(["my-guard", "my-reporter"], runner=fake)

    assert {t.name for t in tools} == {"my-guard", "my-reporter"}
    # explicit list means no org-wide `repo list` call was needed
    assert not any(c[:2] == ["repo", "list"] for c in fake.calls)


def test_is_stale_true_when_no_prior_ledger_entry(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    docs = ToolDocs(
        repo=ToolRepo(name="my-guard", slug="MyThingsLab/my-guard"),
        readme="# my-guard\n",
        claude_md="# guard\n",
    )

    assert is_stale(docs, ledger) is True


def test_is_stale_false_when_hashes_match_last_sync(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    docs = ToolDocs(
        repo=ToolRepo(name="my-guard", slug="MyThingsLab/my-guard"),
        readme="# my-guard\n",
        claude_md="# guard\n",
    )
    ledger.record(
        tool="mydocs",
        kind="docs_sync",
        outcome="success",
        repo=docs.repo.slug,
        readme_hash=docs.readme_hash,
        claude_md_hash=docs.claude_md_hash,
    )

    assert is_stale(docs, ledger) is False


def test_stale_tools_filters_to_changed_only(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.jsonl")
    unchanged = ToolDocs(
        repo=ToolRepo(name="my-reporter", slug="MyThingsLab/my-reporter"),
        readme="# my-reporter\n",
        claude_md="# rep\n",
    )
    ledger.record(
        tool="mydocs", kind="docs_sync", outcome="success", repo=unchanged.repo.slug,
        readme_hash=unchanged.readme_hash, claude_md_hash=unchanged.claude_md_hash,
    )
    changed = ToolDocs(
        repo=ToolRepo(name="my-guard", slug="MyThingsLab/my-guard"),
        readme="# my-guard v2\n",
        claude_md="# guard\n",
    )

    def fetch(repo: ToolRepo) -> ToolDocs:
        return {"my-reporter": unchanged, "my-guard": changed}[repo.name]

    result = stale_tools(
        [unchanged.repo, changed.repo], ledger, fetch=fetch
    )

    assert [d.repo.name for d in result] == ["my-guard"]
