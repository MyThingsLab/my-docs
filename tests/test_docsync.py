from __future__ import annotations

from pathlib import Path

import pytest
from mythings.ledger import Ledger
from mythings.policy import Action, Decision, PolicyResult

from conftest import ScriptedEngine, branch_file, fake_gh, make_docs_site
from mydocs.docsync import DocSync

_CHANGED_README = "# my-guard\n\nThe policy/rule engine.\n"
_CHANGED_CLAUDE = "# my-guard — agent instructions\n\nPurpose: enforce policy.\n"
_UNCHANGED_README = "# my-reporter\n\nLedger digest tool.\n"
_UNCHANGED_CLAUDE = "# my-reporter — agent instructions\n\nPurpose: report.\n"

_PAGE_REPLY = (
    '{"page": {"path": "_tools/my-guard.md", '
    '"content": "---\\ntitle: my-guard\\n---\\n\\nThe policy/rule engine.\\n"}}'
)


def _runner(**kw) -> fake_gh:
    return fake_gh(
        org_repos=["my-guard", "my-reporter", "mythingslab.github.io"],
        files={
            "MyThingsLab/my-guard": {"README.md": _CHANGED_README, "CLAUDE.md": _CHANGED_CLAUDE},
            "MyThingsLab/my-reporter": {
                "README.md": _UNCHANGED_README,
                "CLAUDE.md": _UNCHANGED_CLAUDE,
            },
        },
        **kw,
    )


def _synced_ledger(tmp_path: Path) -> Ledger:
    # Pre-record my-reporter as already synced at its current hashes so it's
    # unchanged in this run; my-guard has no prior record so it's stale.
    from mydocs.fleet import ToolDocs, ToolRepo

    ledger = Ledger(tmp_path / "ledger.jsonl")
    docs = ToolDocs(
        repo=ToolRepo(name="my-reporter", slug="MyThingsLab/my-reporter"),
        readme=_UNCHANGED_README,
        claude_md=_UNCHANGED_CLAUDE,
    )
    ledger.record(
        tool="mydocs",
        kind="docs_sync",
        outcome="success",
        detail="docs page for my-reporter",
        repo=docs.repo.slug,
        page_path="_tools/my-reporter.md",
        readme_hash=docs.readme_hash,
        claude_md_hash=docs.claude_md_hash,
        pr_url="https://github.com/MyThingsLab/mythingslab.github.io/pull/3",
    )
    return ledger


def test_sync_happy_path_one_changed_one_unchanged(tmp_path: Path) -> None:
    site = make_docs_site(tmp_path)
    fake = _runner()
    ledger = _synced_ledger(tmp_path)
    engine = ScriptedEngine(_PAGE_REPLY)
    docsync = DocSync(repo_root=site, repo="MyThingsLab/mythingslab.github.io",
                       ledger=ledger, runner=fake, engine=engine)

    result = docsync.sync(repos=["my-guard", "my-reporter"])

    assert result.outcome == "success"
    assert result.pr == 7
    assert len(engine.calls) == 1  # only the stale tool triggers a call
    assert engine.calls[0].context["tool"] == "my-guard"

    tool_outcomes = {t.tool: t.outcome for t in result.tools}
    assert tool_outcomes == {"my-guard": "success"}

    committed = branch_file(site, "my-docs/sync", "_tools/my-guard.md")
    assert "The policy/rule engine." in committed

    entries = [e for e in ledger if e.data.get("repo") == "MyThingsLab/my-guard"]
    assert entries[-1].kind == "docs_sync"
    assert entries[-1].outcome == "success"
    assert entries[-1].data["pr_url"] == "https://github.com/MyThingsLab/mythingslab.github.io/pull/7"

    reporter_entries = [e for e in ledger if e.data.get("repo") == "MyThingsLab/my-reporter"]
    assert len(reporter_entries) == 1  # no new entry — it was skipped, not re-recorded


def test_sync_nothing_stale_makes_no_engine_call_and_no_pr(tmp_path: Path) -> None:
    site = make_docs_site(tmp_path)
    fake = _runner()
    ledger = _synced_ledger(tmp_path)
    # Also pre-record my-guard at its current hashes so nothing is stale.
    from mydocs.fleet import ToolDocs, ToolRepo

    docs = ToolDocs(
        repo=ToolRepo(name="my-guard", slug="MyThingsLab/my-guard"),
        readme=_CHANGED_README,
        claude_md=_CHANGED_CLAUDE,
    )
    ledger.record(
        tool="mydocs",
        kind="docs_sync",
        outcome="success",
        detail="docs page for my-guard",
        repo=docs.repo.slug,
        page_path="_tools/my-guard.md",
        readme_hash=docs.readme_hash,
        claude_md_hash=docs.claude_md_hash,
        pr_url="https://github.com/MyThingsLab/mythingslab.github.io/pull/3",
    )
    spy = ScriptedEngine("")
    docsync = DocSync(repo_root=site, repo="MyThingsLab/mythingslab.github.io",
                       ledger=ledger, runner=fake, engine=spy)

    result = docsync.sync(repos=["my-guard", "my-reporter"])

    assert result.outcome == "skipped"
    assert result.pr is None
    assert spy.calls == []
    assert not any(c[:2] == ["pr", "create"] for c in fake.calls)


def test_sync_noop_engine_degrades_to_readme_verbatim(tmp_path: Path) -> None:
    site = make_docs_site(tmp_path)
    fake = _runner()
    ledger = _synced_ledger(tmp_path)
    docsync = DocSync(repo_root=site, repo="MyThingsLab/mythingslab.github.io",
                       ledger=ledger, runner=fake)  # default NoopEngine

    result = docsync.sync(repos=["my-guard", "my-reporter"])

    assert result.outcome == "success"
    committed = branch_file(site, "my-docs/sync", "_tools/my-guard.md")
    assert _CHANGED_README.strip() in committed
    assert "title: my-guard" in committed


def test_sync_updates_already_open_pr_branch_without_non_fast_forward_error(
    tmp_path: Path,
) -> None:
    # Regression test for #7: the sync branch is regenerated from base on
    # every run, so pushing again while a PR from a prior run is still open
    # must force-push -- a plain push is rejected as non-fast-forward.
    site = make_docs_site(tmp_path)
    ledger = _synced_ledger(tmp_path)

    fake1 = _runner()
    engine1 = ScriptedEngine(_PAGE_REPLY)
    docsync1 = DocSync(repo_root=site, repo="MyThingsLab/mythingslab.github.io",
                        ledger=ledger, runner=fake1, engine=engine1)
    result1 = docsync1.sync(repos=["my-guard", "my-reporter"])
    assert result1.outcome == "success"
    assert result1.pr == 7

    changed_again_reply = (
        '{"page": {"path": "_tools/my-guard.md", '
        '"content": "---\\ntitle: my-guard\\n---\\n\\nEnforces policy, v2.\\n"}}'
    )
    fake2 = fake_gh(
        org_repos=["my-guard", "my-reporter", "mythingslab.github.io"],
        files={
            "MyThingsLab/my-guard": {
                "README.md": "# my-guard\n\nThe policy/rule engine, v2.\n",
                "CLAUDE.md": _CHANGED_CLAUDE,
            },
        },
        existing_pr={"number": 7, "url": "https://github.com/MyThingsLab/mythingslab.github.io/pull/7"},
    )
    engine2 = ScriptedEngine(changed_again_reply)
    docsync2 = DocSync(repo_root=site, repo="MyThingsLab/mythingslab.github.io",
                        ledger=ledger, runner=fake2, engine=engine2)

    result2 = docsync2.sync(repos=["my-guard"])

    assert result2.outcome == "success"
    assert result2.pr == 7
    committed = branch_file(site, "my-docs/sync", "_tools/my-guard.md")
    assert "Enforces policy, v2." in committed


def test_sync_no_pr_skips_opening_pr(tmp_path: Path) -> None:
    site = make_docs_site(tmp_path)
    fake = _runner()
    ledger = _synced_ledger(tmp_path)
    engine = ScriptedEngine(_PAGE_REPLY)
    docsync = DocSync(repo_root=site, repo="MyThingsLab/mythingslab.github.io",
                       ledger=ledger, runner=fake, engine=engine)

    result = docsync.sync(repos=["my-guard", "my-reporter"], no_pr=True)

    assert result.outcome == "success"
    assert result.pr is None
    assert not any(c[:2] == ["pr", "create"] for c in fake.calls)


class _DenyPolicy:
    def evaluate(self, action: Action) -> PolicyResult:
        return PolicyResult(Decision.DENY, reason="blocked for test", rule="test_deny")


def test_sync_records_failure_when_policy_denies_the_pr(tmp_path: Path) -> None:
    site = make_docs_site(tmp_path)
    fake = _runner()
    ledger = _synced_ledger(tmp_path)
    engine = ScriptedEngine(_PAGE_REPLY)
    docsync = DocSync(repo_root=site, repo="MyThingsLab/mythingslab.github.io",
                       ledger=ledger, runner=fake, engine=engine, policy=_DenyPolicy())

    result = docsync.sync(repos=["my-guard", "my-reporter"])

    assert result.outcome == "failure"
    assert result.pr is None
    assert "policy blocked" in result.detail
    failures = [e for e in ledger if e.outcome == "failure"]
    assert len(failures) == 1
    assert failures[0].detail == result.detail


def test_style_anchor_returns_decoded_existing_page(tmp_path: Path) -> None:
    site = make_docs_site(tmp_path)
    anchor_content = "---\ntitle: my-researcher\n---\n\nExisting page.\n"
    fake = fake_gh(
        org_repos=["my-guard", "mythingslab.github.io"],
        files={
            "MyThingsLab/my-guard": {"README.md": _CHANGED_README, "CLAUDE.md": _CHANGED_CLAUDE},
            "MyThingsLab/mythingslab.github.io": {
                "_tools/my-researcher.md": anchor_content,
            },
        },
    )
    ledger = _synced_ledger(tmp_path)
    docsync = DocSync(repo_root=site, repo="MyThingsLab/mythingslab.github.io",
                       ledger=ledger, runner=fake)

    anchor = docsync._style_anchor()

    assert anchor == anchor_content


def test_git_failure_raises_runtime_error_with_stderr(tmp_path: Path) -> None:
    site = make_docs_site(tmp_path)
    fake = _runner()
    ledger = _synced_ledger(tmp_path)
    engine = ScriptedEngine(_PAGE_REPLY)
    docsync = DocSync(repo_root=site, repo="MyThingsLab/mythingslab.github.io",
                       ledger=ledger, runner=fake, engine=engine)

    with pytest.raises(RuntimeError, match="git bogus-not-a-command failed"):
        docsync._git(site, ["bogus-not-a-command"])
