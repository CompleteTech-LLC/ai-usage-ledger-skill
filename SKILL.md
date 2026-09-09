---
name: ai-usage-ledger
description: >-
  Compile every locally recorded AI coding-agent model call (Claude Code, Codex CLI/Desktop, GitHub Copilot CLI, Gemini CLI, opencode, OpenClaw, Cline/Roo/Kilo, aider, Kimi Code, Mistral Vibe, Continue, pi, Codebuff and any JSON-logging tool) across all drives, WSL distros and SSH hosts into one de-duplicated event log; price it at list API rates; split it by subscription account and billing plan; validate it against the tools' own counters; and render a CompleteTech-branded light/dark dashboard plus a research-grade study package. Use when asked to "find all my AI logs", "how many tokens did I use", "what would this have cost on the API", "compare my subscriptions", "usage by account", "cache savings", or to refresh an existing ledger.
version: 1.2.0
metadata:
  openclaw:
    skillKey: ai-usage-ledger
    homepage: https://github.com/CompleteTech-LLC/ai-usage-ledger-skill
    requires:
      bins:
        - python3
    install:
      - kind: uv
        package: pyyaml==6.0.3
---

# AI Usage Ledger Skill

## Purpose

| Use | Scope |
|---|---|
| Usage ledger | Locate, de-duplicate, price and attribute every locally recorded AI coding-agent call on a person's machines. |
| Starting point | Any request to count tokens, estimate API-equivalent cost, compare subscriptions, or break usage down by account, model, project or time. |
| Operating boundary | Read-only over the tools' directories; identity claims are decoded, never credentials; nothing is transmitted. |

## System Boundary

| Boundary | Use |
|---|---|
| This skill | Discovery, scanning, de-duplication, pricing, account attribution, validation, dashboard and study rendering. |
| Provider consoles and exports | Invoices and billed amounts. This skill produces API-equivalents at list price, not invoices. |
| `agentic-invoice-skill` | Billing a client for agentic work; feed it verified figures from the ledger. |
| `agentic-security-review-skill` | Questions about what the transcripts contain or who may read them. |
| Vendor usage dashboards (Codex app, Cursor, Windsurf, Copilot) | Their own counters; several include replayed history or omit tokens, see `references/harness-catalog.md`. |

## Core Workflow

| Step | Action |
|---|---|
| 1 | Discover every profile, drive, WSL distro and host per `references/discovery.md`; check every applicable row of `references/harness-catalog.md`. Record what could not be read and why. |
| 2 | Read credential files to list accounts (ChatGPT account ids and plans, Claude e-mails and tiers, usage-based orgs). Decode claims only. |
| 3 | Write `manifest.json`, `pricing.json`, `accounts.json` and `report_config.json` from `templates/` and `examples/`. |
| 4 | Run `python3 scripts/run_pipeline.py --manifest manifest.json`. |
| 5 | Validate per the checks below; rebuild once if a rule was wrong. |
| 6 | Deliver the dashboard, the study package and `all_events.csv`, with exclusions and low-confidence rules stated. |

| Required Fact | Examples |
|---|---|
| Hosts and roots | Every `~/.claude`, `~/.codex`, IDE `globalStorage`, gateway `sessions/` directory, with size and date range. |
| Accounts | `chatgpt_account_id` prefix, plan type and e-mail from each `auth.json`; `oauthAccount` from each `.claude.json`. |
| Prices | List rates per model on the snapshot date, with `assumed` rows named. |
| Exclusions | Locked directories, closed SSH ports, tools without token fields. |

## Validation Checks

| Check | Requirement |
|---|---|
| Replay proof | One spawned Codex thread's burst equals the parent's first N events value for value and was skipped; a small `codex_replay_skipped` on a host with sub-agents means the rule is not firing. |
| Counter cross-check | Non-forked Codex threads within 2% of `state_5.sqlite`; spawned children explained; Claude `stats-cache.json` ≥ transcript figure. |
| Plan field | Codex calls mostly `pro`/`plus`, some `self_serve_business_usage_based` where a prepaid org exists, `?` only for old clients. |
| Generic rows | Anything with `granularity: generic` verified against two source files as per-call, not cumulative. |
| Magnitude | Median Codex context per call 100 to 200K tokens; hundreds of billions per month on one subscription is a replay bug. |
| Fixtures | `python3 tests/make_fixtures.py` prints `ALL OK` before the first real run. |

## Quality Rules

| Rule | Requirement |
|---|---|
| Read-only | Never modify, delete or "clean up" agent directories; do not `wsl --shutdown` while agents run. |
| Secrets | Decode `id_token` claims for identity; never print or copy tokens or API keys. |
| Evidence classes | Keep class A (per-call records), class B (tool counters) and class C (priced estimates) apart in every table. |
| Confidence | Every finding and every attribution rule carries a confidence level and its evidence. |
| Unknowns | Price unpublished models at a stated sibling marked `assumed`; report the share of cost that rests on them. |
| Corrections | When a rerun changes a previously reported figure, state the cause alongside the new number. |

## Resource Guide

| Resource | Role |
|---|---|
| `references/harness-catalog.md` | Forty-plus agents, IDE assistants, gateways and runtimes: paths per OS, record shapes, token fields, scanner support. |
| `references/log-formats.md` | Exact fields per built-in parser, de-duplication and replay rules, normalised schema. |
| `references/discovery.md` | Where logs and credentials live, sweep commands, reading accounts safely, defensible attribution rules. |
| `references/pitfalls.md` | Sixteen ways the numbers go wrong. |
| `references/harnesses.md` | Install locations and notes for Claude Code, Codex, Cursor, SSH, WSL and macOS. |
| `templates/` | Manifest, pricing sheet, account and report-config examples. |
| `examples/` | A workstation manifest and the CompleteTech brand preset. |
| `scripts/run_pipeline.py` | One command: scan every host, merge, analyse, render, zip. |
| `scripts/compile_ai_logs.py` | `scan` (14 parsers plus a generic sniffer) and `report` (merge, price, attribute). |
| `scripts/analyze_events.py` | Distributions, time of day, concentration, validation, sensitivity. |
| `scripts/build_dashboard.py`, `scripts/build_report.py` | Branded dashboard and study package. |
| `tests/make_fixtures.py` | Synthetic logs and totals check for every parser. |

## Runtime Permissions

| Capability | Boundary |
|---|---|
| Files read | Agent transcripts, tool databases and credential files under the user's own profiles and hosts named in the manifest; bundled templates, references and `assets/logo.png`. |
| Files written | Only `scans/`, `compiled/` and `reports/` under the manifest's `workdir`, and `tests/fixtures`, `tests/out` during the fixture suite. |
| Local commands | `python3` for the scripts; `wsl.exe`, `ssh` and `scp` only for hosts declared in the manifest. |
| Not required | Outbound network access (pricing pages are fetched by the operator, not the scripts), credential use, persistence, privilege escalation, destructive file operations, background services. |

## Renderer

| Task | Command |
|---|---|
| Full run | `python3 scripts/run_pipeline.py --manifest manifest.json` |
| Re-price or re-brand without rescanning | `python3 scripts/run_pipeline.py --manifest manifest.json --only report,analyze,build` |
| Scan a subset of hosts | `python3 scripts/run_pipeline.py --manifest manifest.json --hosts windows,wsl-ubuntu` |
| Parser self-test | `python3 tests/make_fixtures.py` |
| Quality gate | `python3 scripts/validate_quality.py` |

| Output | Path |
|---|---|
| Event log (primary artefact) | `compiled/all_events.csv` |
| Aggregates | `compiled/by_*.csv`, `subscription_vs_api*.csv`, `SUMMARY.md`, `summary.json`, `analysis.json` |
| Dashboard | `compiled/agent-ledger.html` |
| Study package | `reports/<prefix>_<date>/` (`USAGE_REPORT.md`, `report.html`, `ledger.json`, `pricing.json`, `accounts.json`, `README.md`, `SHA256SUMS`) and `.zip` |

## Branding and Themes

| Element | Source |
|---|---|
| Brand preset | `examples/report_config.completetech.json`: CompleteTech LLC logo, eyebrow, tagline, contact, footer and palette (`#1E3A8A` accent, `#0F172A` ink, `#EEF2FF` soft accent, `#64748B` muted, `#E2E8F0` border, `#F8FAFC` zebra). |
| Logo | `assets/logo.png`, inlined as a data URI so both pages stay self-contained. |
| Themes | Light, dark and system in both pages via `prefers-color-scheme`, a fixed Light / System / Dark toggle persisted in the browser, and an explicit `data-theme` stamp from a host. |
| Overrides | `branding.light` / `branding.dark` may set any token (`bg`, `surface`, `surface-2`, `ink`, `ink-2`, `ink-3`, `line`, `line-2`, tool colours, `seq1..seq7`); fonts via `google_fonts_url`; `extra_css` appended verbatim. Keep tool colours CVD-safe. |

## Definitions

`input_uncached` fresh prompt tokens · `cache_read` served from cache · `cache_write` written to cache (Anthropic, split 5m/1h) · `output` incl. reasoning · `total` = sum. API-equivalent = tokens × list price. Cache saving = same call priced with all prompt tokens uncached, minus actual. Subscription months are counted only when that account made a call. Usage-based calls are real spend and stay out of the subscription comparison.

## Network Boundary

| Boundary | Requirement |
|---|---|
| Local-only runtime | The scripts make no outbound network calls; SSH and WSL are used only for hosts the operator names in the manifest. |
| Publishing | Dashboards and study packages are published only when the operator asks (Artifacts, files, or a repository). |
| Data | Scanned transcripts and the compiled ledger never leave the operator's machines through this skill. |
