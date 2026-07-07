from __future__ import annotations

from mythings.engine import NoopEngine

from conftest import ScriptedEngine
from mydocs.fleet import ToolDocs, ToolRepo
from mydocs.page import render_page


def _docs() -> ToolDocs:
    return ToolDocs(
        repo=ToolRepo(name="my-guard", slug="MyThingsLab/my-guard"),
        readme="# my-guard\n\nThe policy/rule engine.\n",
        claude_md="# my-guard — agent instructions\n\nPurpose: enforce policy.\n",
    )


def test_render_page_parses_scripted_engine_reply() -> None:
    reply = (
        '{"page": {"path": "_tools/my-guard.md", '
        '"content": "---\\ntitle: my-guard\\n---\\n\\nEnforces policy.\\n"}}'
    )
    engine = ScriptedEngine(reply)

    page = render_page(engine, _docs(), style_anchor="---\ntitle: anchor\n---\n")

    assert page.path == "_tools/my-guard.md"
    assert "Enforces policy." in page.content
    assert page.degraded is False


def test_render_page_against_noop_engine_degrades_to_readme_verbatim() -> None:
    page = render_page(NoopEngine(), _docs(), style_anchor="")

    assert page.degraded is True
    assert page.path == "_tools/my-guard.md"
    assert "The policy/rule engine." in page.content
    assert "title: my-guard" in page.content


def test_render_page_degrades_on_unparseable_reply() -> None:
    engine = ScriptedEngine("not json at all")

    page = render_page(engine, _docs(), style_anchor="")

    assert page.degraded is True
    assert "The policy/rule engine." in page.content
