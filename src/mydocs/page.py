from __future__ import annotations

import json
from dataclasses import dataclass

from mythings.engine import Engine, EngineRequest

from mydocs.fleet import ToolDocs

_PAGE_SYSTEM = (
    "You write technical-docs pages for a fleet of developer tools. Ground "
    "every claim ONLY in the given README and CLAUDE.md content -- never "
    "invent a capability, invariant, or detail not stated in either source. "
    "Match the style (front matter shape, section order, tone) of the given "
    "existing docs-site page. Reply with a single JSON object and nothing else."
)


@dataclass(frozen=True)
class Page:
    path: str
    content: str
    degraded: bool


def _parse_json_object(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(lines).strip()
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _prompt(docs: ToolDocs, style_anchor: str) -> str:
    return (
        f"Tool: {docs.repo.name}\n"
        f"Repo: {docs.repo.slug}\n\n"
        f"README.md:\n{docs.readme}\n\n"
        f"CLAUDE.md:\n{docs.claude_md}\n\n"
        f"Existing docs-site page (style anchor):\n{style_anchor}\n\n"
        'Return JSON with keys: "path" (string, "_tools/<name>.md") and '
        '"content" (string, the full markdown file: front matter + body).'
    )


def _front_matter(name: str, slug: str) -> str:
    return f"---\ntitle: {name}\nrepo: https://github.com/{slug}\n---\n\n"


def _degraded_page(docs: ToolDocs) -> Page:
    # Honest degrade: no synthesis, the README verbatim under templated front
    # matter -- never a fabricated description.
    content = _front_matter(docs.repo.name, docs.repo.slug) + docs.readme
    return Page(path=f"_tools/{docs.repo.name}.md", content=content, degraded=True)


def render_page(engine: Engine, docs: ToolDocs, style_anchor: str) -> Page:
    reply = engine.run(
        EngineRequest(
            system=_PAGE_SYSTEM,
            prompt=_prompt(docs, style_anchor),
            context={"tool": docs.repo.name, "repo": docs.repo.slug},
        )
    )
    obj = _parse_json_object(reply.text)
    if obj is None:
        return _degraded_page(docs)

    page = obj.get("page") if isinstance(obj.get("page"), dict) else obj
    path = str(page.get("path", "")).strip() or f"_tools/{docs.repo.name}.md"
    content = str(page.get("content", "")).strip()
    if not content:
        return _degraded_page(docs)
    return Page(path=path, content=content, degraded=False)
