from __future__ import annotations

from pathlib import Path

import pytest
from mythings.engine import ClaudeCLIEngine, NoopEngine

from conftest import branch_file, fake_gh, make_docs_site
from mydocs import cli

_CHANGED_README = "# my-guard\n\nThe policy/rule engine.\n"
_CHANGED_CLAUDE = "# my-guard — agent instructions\n\nPurpose: enforce policy.\n"


def test_build_engine_maps_names_to_expected_backends() -> None:
    assert isinstance(cli.build_engine("noop"), NoopEngine)
    assert isinstance(cli.build_engine("claude-cli"), ClaudeCLIEngine)


def test_build_engine_passes_model_through_to_claude_cli() -> None:
    engine = cli.build_engine("claude-cli", model="haiku")
    assert isinstance(engine, ClaudeCLIEngine)
    assert engine._model == "haiku"


def _patch_gh(monkeypatch: pytest.MonkeyPatch, fake) -> None:
    # Patch the `gh` boundary at the CLI's DocSync construction, same pattern
    # my-site's tests use: swap the runner in after real _make() builds it.
    real_make = cli._make

    def _make(args):  # noqa: ANN001
        docsync = real_make(args)
        docsync.runner = fake
        docsync.github._run = fake
        return docsync

    monkeypatch.setattr(cli, "_make", _make)


def test_sync_requires_repos_or_all() -> None:
    with pytest.raises(SystemExit):
        cli.main(["sync", "--repo-root", "."])


def test_missing_subcommand_is_a_usage_error() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


def test_sync_prints_success_line_and_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = make_docs_site(tmp_path)
    fake = fake_gh(
        org_repos=["my-guard", "mythingslab.github.io"],
        files={
            "MyThingsLab/my-guard": {"README.md": _CHANGED_README, "CLAUDE.md": _CHANGED_CLAUDE},
        },
    )
    _patch_gh(monkeypatch, fake)

    code = cli.main(
        [
            "sync",
            "--repos", "my-guard",
            "--repo-root", str(site),
            "--ledger", str(tmp_path / "ledger.jsonl"),
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "success:" in out
    assert "PR #7" in out
    committed = branch_file(site, "my-docs/sync", "_tools/my-guard.md")
    assert _CHANGED_README.strip() in committed  # NoopEngine degrades verbatim


def test_sync_all_flag_enumerates_the_whole_org(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = make_docs_site(tmp_path)
    fake = fake_gh(
        org_repos=["my-guard", "mythingslab.github.io"],
        files={
            "MyThingsLab/my-guard": {"README.md": _CHANGED_README, "CLAUDE.md": _CHANGED_CLAUDE},
        },
    )
    _patch_gh(monkeypatch, fake)

    code = cli.main(
        [
            "sync",
            "--all",
            "--repo-root", str(site),
            "--ledger", str(tmp_path / "ledger.jsonl"),
        ]
    )

    assert code == 0
    assert any(c[:2] == ["repo", "list"] for c in fake.calls)  # --all triggers org enumeration


def test_sync_no_pr_flag_skips_opening_a_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = make_docs_site(tmp_path)
    fake = fake_gh(
        org_repos=["my-guard", "mythingslab.github.io"],
        files={
            "MyThingsLab/my-guard": {"README.md": _CHANGED_README, "CLAUDE.md": _CHANGED_CLAUDE},
        },
    )
    _patch_gh(monkeypatch, fake)

    code = cli.main(
        [
            "sync",
            "--repos", "my-guard",
            "--repo-root", str(site),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--no-pr",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "PR #" not in out
    assert not any(c[:2] == ["pr", "create"] for c in fake.calls)


def test_sync_failure_outcome_returns_exit_code_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = make_docs_site(tmp_path)
    fake = fake_gh(
        org_repos=["my-guard", "mythingslab.github.io"],
        files={
            "MyThingsLab/my-guard": {"README.md": _CHANGED_README, "CLAUDE.md": _CHANGED_CLAUDE},
        },
    )
    _patch_gh(monkeypatch, fake)
    from mythings.policy import Action, Decision, PolicyResult

    real_make = cli._make

    def _make(args):  # noqa: ANN001
        docsync = real_make(args)
        docsync.runner = fake
        docsync.github._run = fake

        class _DenyPolicy:
            def evaluate(self, action: Action) -> PolicyResult:
                return PolicyResult(Decision.DENY, reason="blocked for test", rule="test_deny")

        docsync.policy = _DenyPolicy()
        return docsync

    monkeypatch.setattr(cli, "_make", _make)

    code = cli.main(
        [
            "sync",
            "--repos", "my-guard",
            "--repo-root", str(site),
            "--ledger", str(tmp_path / "ledger.jsonl"),
        ]
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "failure:" in out


def test_sync_engine_claude_cli_flag_builds_that_engine_without_invoking_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = make_docs_site(tmp_path)
    fake = fake_gh(org_repos=["mythingslab.github.io"], files={})
    _patch_gh(monkeypatch, fake)

    # No stale tools -> sync short-circuits before any Engine.run() call, so
    # this exercises --engine claude-cli wiring without a real `claude` call.
    code = cli.main(
        [
            "sync",
            "--repos", "",
            "--all",
            "--repo-root", str(site),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--engine", "claude-cli",
            "--engine-model", "haiku",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "skipped:" in out
