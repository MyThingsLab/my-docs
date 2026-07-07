# my-docs

[![CI](https://github.com/MyThingsLab/my-docs/actions/workflows/ci.yml/badge.svg)](https://github.com/MyThingsLab/my-docs/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/MyThingsLab/my-docs/branch/main/graph/badge.svg)](https://codecov.io/gh/MyThingsLab/my-docs)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![MIT](https://img.shields.io/badge/license-MIT-green)

A [MyThingsLab](../mythings-core) `My[X]` tool: keeps
`MyThingsLab/mythingslab.github.io` — the fleet's technical-docs site — in
sync with the fleet itself. One docs page per `My[X]` tool, refreshed from
that tool's `README.md` + `CLAUDE.md` whenever they change.

MyDocs is deliberately narrow: it publishes what a tool's own README/
CLAUDE.md already say, in a consistent site layout. It does not review,
critique, or invent capability descriptions — that discipline keeps its one
Engine call a formatting/prose step, not a judgment call about what a tool
does.

## Usage

```bash
# Sync every MyThingsLab repo with a CLAUDE.md into the docs site (one PR).
mydocs sync --all --engine claude-cli

# Targeted re-sync of specific tools:
mydocs sync --repos my-guard,my-researcher --engine claude-cli

# Dry run — compute the stale list and render pages, skip opening a PR:
mydocs sync --all --no-pr
```

Each stale tool gets **exactly one** Engine call. Against the default
`--engine noop` (zero tokens), a tool's page is the README verbatim under
templated front matter — an honest degrade, never a fabricated description.
If nothing is stale, the run makes zero Engine calls and opens no PR.

## Staleness

For each candidate tool repo, `mydocs` hashes `README.md` + `CLAUDE.md` and
compares against the hash recorded in that tool's last `kind=docs_sync`
ledger entry. Only tools whose hash changed since the last sync are
re-rendered; all stale tools in one run share a single PR (one commit per
tool's page) against the docs site.

## Install (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ../mythings-core -e ../my-guard -e ".[dev]"
pytest
```

See [`CLAUDE.md`](CLAUDE.md) for the tool's seams and [`HARNESS.md`](HARNESS.md)
for the inherited build rules.

## License

MIT — see [`LICENSE`](LICENSE).
