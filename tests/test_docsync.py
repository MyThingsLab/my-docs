from __future__ import annotations

from pathlib import Path

from mythings.ledger import Ledger

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
