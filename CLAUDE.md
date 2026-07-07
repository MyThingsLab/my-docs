# my-docs — agent instructions

You are developing **my-docs**, a MyThingsLab My[X] tool.

**Inherited rules:** obey [`./HARNESS.md`](./HARNESS.md) in full — the vendored
MyThingsLab build-harness rules. Do not restate or override them. Anything not
covered here defers to `HARNESS.md`, then `mythings-core/docs/CONVENTIONS.md`.

## This tool

- **Purpose:** keeps `MyThingsLab/mythingslab.github.io` — the fleet's
  technical-docs site — in sync with the fleet itself: one docs page
  (`_tools/<name>.md`) per `My[X]` tool, refreshed from that tool's
  `README.md` + `CLAUDE.md` whenever they change. Publishes what a tool's own
  README/CLAUDE.md already say, in a consistent site layout — it does not
  review, critique, or invent capability descriptions.
- **The single Engine call:** one per stale tool: "write or update this
  tool's docs page from its README and filled CLAUDE.md seams, matching the
  style of an existing docs-site page" → `{page: {path, content}}`. The model
  may only draw on the given README/CLAUDE.md content — no claims about
  behavior not stated in either source. Against `NoopEngine`, degrades to
  copying the README verbatim under a templated front matter — honest
  degrade, no fabricated description.
- **Invariants / rules:** deterministic pre-work only, no model call: enumerate
  `MyThingsLab` org repos with a `CLAUDE.md`, hash each tool's `README.md` +
  `CLAUDE.md`, and compare against the hash recorded in that tool's last
  `kind=docs_sync` ledger entry to build the stale list. If nothing is stale,
  skip entirely — zero Engine calls, no PR, `outcome=skipped`. One Engine call
  **per stale tool** (never one call for the whole batch), but all stale
  tools in a run share **one PR** against `mythingslab.github.io` (one commit
  per tool's page). Read-only against every source tool repo — the only
  side effect is the docs-site PR. **Never merges.**
- **Backlog label:** `my-docs`
