# AI Usage Ledger Skill

<p align="center">
  <img src="assets/logo.png" alt="CompleteTech LLC logo" width="260">
</p>

A CompleteTech LLC skill for compiling every locally recorded AI coding-agent call into one priced, account-attributed, validated ledger, rendered as a branded light/dark dashboard and a research-grade study package.

## About

Part of the CompleteTech LLC agentic services skill library. Where the `agentic-*` skills produce client-facing documents, this skill produces the evidence behind them: how much agent work happened, on which accounts, what it would have cost at list price, and what the cache and the subscriptions saved.

## OpenClaw / ClawHub Metadata

- Skill key: `ai-usage-ledger`
- Version-ready metadata: `1.2.0`
- Homepage: https://github.com/CompleteTech-LLC/ai-usage-ledger-skill
- README: https://github.com/CompleteTech-LLC/ai-usage-ledger-skill#readme
- Runtime binaries: `python3`
- Python packages: none at runtime (standard library); `pyyaml==6.0.3` and `ruff==0.14.0` for the quality validator
- Intended registry/discovery tags: `latest`, `complete-tech`, `codex-skill`, `claude-code`, `codex`, `token-usage`, `cost-analysis`, `observability`, `ledger`, `dashboard`
- License: repository code, templates, and documentation use MIT; published by CompleteTech on ClawHub.
- Brand assets: CompleteTech LLC names, logos, seals, and brand assets are reserved; see `BRAND_ASSETS.md`.

## Workflow Diagram

Source: [assets/diagrams/workflow.mmd](assets/diagrams/workflow.mmd).

```mermaid
flowchart LR
  A[Discover logs and accounts] --> B[Manifest, pricing, accounts, branding]
  B --> C[Scan each host]
  C --> D[Merge, de-duplicate, price, attribute]
  D --> E{Validated?}
  E -->|No| F[Fix rules or replay filter]
  F --> C
  E -->|Yes| G[Dashboard and study package]
  classDef source fill:#eef6ff,stroke:#3778c2,color:#102a43;
  classDef gate fill:#fff7e6,stroke:#c97a12,color:#3d2600;
  classDef output fill:#eefaf0,stroke:#2f8f46,color:#12351d;
  class A,B,C,D source;
  class E gate;
  class F,G output;
```

## What It Does

- Finds agent logs on every drive, user profile, WSL distro and SSH host, including old-profile backups.
- Parses Claude Code / Agent SDK, Codex CLI / Desktop / VS Code, GitHub Copilot CLI, Gemini CLI, Qwen Code, opencode, OpenClaw, pi, Cline / Roo Code / Kilo Code, aider, Kimi Code CLI, Mistral Vibe and Continue with dedicated parsers, and any other JSON-logging tool through a generic usage sniffer.
- De-duplicates streamed turns and Codex fork replay (the copy of a parent's history that every spawned thread carries), which otherwise inflates totals by an order of magnitude.
- Prices every call at list API rates by token class, computes cache savings, and compares each subscription account with its API-equivalent using the billing plan Codex stamps on each call.
- Validates against the tools' own counters and states confidence per finding and per attribution rule.
- Renders a themed, brandable dashboard and a dated, checksummed study package with a machine-readable ledger.

## Contents

- `SKILL.md` - operating instructions, validation checks and boundaries.
- `scripts/run_pipeline.py` - one command from raw logs to the packaged ledger.
- `scripts/compile_ai_logs.py` - `scan` (14 parsers plus a generic sniffer) and `report` (merge, price, attribute).
- `scripts/analyze_events.py` - distributions, time of day, concentration, validation, sensitivity.
- `scripts/build_dashboard.py`, `scripts/build_report.py` - branded dashboard and study renderers.
- `scripts/validate_quality.py` - lint, parse, diagram, smoke, fixture and ClawHub bundle gates.
- `templates/` - manifest, pricing sheet, account and report-config examples.
- `examples/` - a workstation manifest and the CompleteTech brand preset.
- `references/` - harness and runtime catalog (forty-plus tools), log formats, discovery and account attribution, pitfalls, harness notes.
- `tests/make_fixtures.py` - synthetic logs and totals check for every parser.

## Quick Start

```bash
pip install -r requirements.txt            # only for the quality validator; the pipeline is stdlib
python3 tests/make_fixtures.py             # must print ALL OK
cp examples/manifest.workstation.json manifest.json
cp examples/report_config.completetech.json report_config.completetech.json
cp templates/pricing.json templates/accounts.example.json .   # edit prices, rename accounts.example.json to accounts.json
python3 scripts/run_pipeline.py --manifest manifest.json
```

Rendered figures are API-equivalents at list price, not invoices. Attribution rules below high confidence are listed in the study; challenge those first.

## Example

![Study preview](assets/examples/example.png)

Example files: [Markdown](assets/examples/example.md) · [HTML dashboard](assets/examples/example.html).

**Study: synthetic fixture data across ten tools**

- Ten parsers exercised on generated logs, including a forked Codex thread whose replayed history is dropped.
- Per-account subscription versus API-equivalent, usage-based spend, and cache savings tables.
- Validation, distributions, time-of-day and concentration sections with confidence levels.

Generate it in one command:

```bash
python3 tests/make_fixtures.py
python3 scripts/run_pipeline.py --manifest examples/manifest.fixtures.json
```

The committed example uses synthetic fixture data only; no real account or transcript is included.

## Branding Assets

`assets/logo.png` is the CompleteTech LLC logo used on the dashboard and study headers. `examples/report_config.completetech.json` carries the palette (`#1E3A8A` accent, `#0F172A` ink, `#EEF2FF` soft accent, `#64748B` muted, `#E2E8F0` border, `#F8FAFC` zebra), eyebrow, tagline and footer used across the skill library. Both pages render in light, dark and system themes with a persisted toggle.

## Brand Notes

Use a direct, concrete, low-hype tone. Present figures as measured evidence with stated confidence: what was scanned, what was excluded, which rules are inferred. Do not present API-equivalents as invoices, do not smooth over corrections, and do not quote vendor dashboards that include replayed history as independent confirmation.

## Runtime Permissions

| Capability | Boundary |
|---|---|
| Files read | Agent transcripts, tool databases and credential files under the operator's own profiles and manifest hosts; bundled templates, references, `assets/logo.png`. |
| Files written | Only `scans/`, `compiled/` and `reports/` under the manifest `workdir`, and test fixtures during the fixture suite. |
| Local commands | `python3` scripts; `wsl.exe`, `ssh`, `scp` only for hosts declared in the manifest. |
| Not required | Outbound network access, credential use, persistence, privilege escalation, destructive file operations, background services. |

## License

Code, templates, and documentation are licensed under the MIT License. CompleteTech LLC names, logos, seals, and brand assets are reserved and are not licensed for reuse except to identify this project. See `LICENSE` and `BRAND_ASSETS.md`.

## Network Boundary

This skill is local-only. The scripts make no outbound network calls and post no metadata anywhere; SSH and WSL are reached only for hosts the operator names.
