---
name: ai-usage-ledger
description: >-
  Compile every locally recorded AI coding-agent model call (Claude Code, Codex CLI/Desktop, GitHub Copilot CLI, Gemini CLI, opencode, OpenClaw, Cline/Roo/Kilo, aider, Kimi Code, Mistral Vibe, Continue, pi, Codebuff and any JSON-logging tool) across all drives, user profiles, WSL distros and SSH hosts into one append-only, de-duplicated ledger stored as SQLite, JSON or CSV; price it at list API rates; split it by subscription account and billing plan; validate it against the tools' own counters; and render a branded light/dark dashboard plus a research-grade study package. Onboards once (branding, theme, storage backend, scheduled refresh, anonymised publication copy; hosts and accounts auto-detected per OS), remembers the preferences, refreshes with one command or on a schedule, renders fifteen ledger documents (statements, memos, briefs, billing evidence) as Markdown, HTML, PDF and DOCX, can anonymise everything for publication, optionally archives the raw log files themselves so they outlive the tools' retention, and answers detailed questions (per day, project, account, model, session, prompt text, or inside the archived logs) through a query layer over the accumulated store. Use when asked to "find all my AI logs", "how many tokens did I use", "what would this have cost on the API", "compare my subscriptions", "usage by account", "cache savings", "set up my usage ledger", "monthly usage statement", "publish my usage anonymously", "how much did I use last Tuesday", "which sessions cost the most", "when did I first use model X", "find the session where I asked about Y", or to refresh an existing ledger.
version: 1.5.4
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
| Operating boundary | Read-only over the tools' directories; identity claims are decoded, never credentials; nothing is transmitted. The ledger store is append-only: nothing already stored is edited or removed. |

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
| 1 | First use only: onboard. Reports are unbranded until the operator chooses branding: answer the first prompt (`none`, or a named preset such as `completetech`), pass `--brand-preset <name>`, or set `brand.*` values; unattended `init --yes` stays neutral and `run` refuses to start without a config. On a terminal run `python3 scripts/ledger.py init` and answer the prompts. From an agent harness, ask the operator the same questions in chat (brand name, eyebrow, tagline, contact, logo, accent colour, theme, storage backend, working directory, timezone, whether to include other profiles / drives / WSL, whether to build an anonymised copy on every run, whether to archive the raw log files themselves (and compress them), and whether to refresh on a schedule: none / daily / weekly / monthly, time, weekday, install now), then run `python3 scripts/ledger.py init --yes --set key=value ...`. Preferences persist in `~/.ai-usage-ledger/config.json` and in the store; later runs never ask again. Installing the schedule changes the operator's Task Scheduler or crontab, so confirm it explicitly before passing `schedule.install=y`. |
| 2 | Onboarding auto-detects hosts and roots for this OS (`scripts/detect_hosts.py`: Windows, macOS, Linux, every WSL distro, other user profiles and drives, VS Code-family global storage, `CODEX_HOME`-style overrides) and drafts `accounts.json` from credential claims. Review the draft: labels, prices, and the `why` on each rule. Add SSH hosts when prompted or in `config.json` `extra_hosts`. Record what could not be read and why. |
| 3 | Run `python3 scripts/ledger.py run`. It rescans, archives the raw files when `archive.raw_logs` is on, appends only new calls to the store (stable ids; duplicates are skipped), rebuilds the tables, dashboard and study package, and records the run. Repeat as often as wanted. |
| 4 | Validate per the checks below; fix a rule and run `python3 scripts/ledger.py run --no-scan` to rebuild from the store without rescanning. |
| 5 | Deliver the dashboard, the study package and `all_events.csv` (or `ledger.py export`), with exclusions and low-confidence rules stated. For a statement, memo or brief, pick a template from `references/ledger-document-catalog.md` and render it with `python3 scripts/ledger.py doc --template <id> --var prepared_for=... [--pdf --docx]`. For anything leaving the organisation, use the anonymised copy (`ledger.py run --anonymize`, then `doc --anonymize`) and check the outputs for names before publishing. |
| 6 | To start over (new brand, different backend, changed hosts) run `python3 scripts/ledger.py reinit`; the previous store is kept beside the new one with a timestamp. The manual route (`run_pipeline.py` with a hand-written manifest) still works for one-off or unattended use. |
| 7 | When the operator asks a specific question ("how many tokens on Tuesday", "which project cost the most in August", "when did I first use gpt-6", "what did I ask about rate limits"), answer it from the store with `python3 scripts/ledger.py query <preset> [filters]` per the Answering Detailed Questions table, not from the summary tables; go into the archived raw logs (`query logs`) when the answer is in the transcript rather than the counts. |

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
| Fixtures | `python3 tests/make_fixtures.py` prints `ALL OK` and `python3 tests/test_store.py` prints `STORE OK` before the first real run. |
| Append-only | A second `ledger.py run` straight after the first reports `added {"events": 0, ...}`; a host that adds events on every run without new activity is being counted twice (check `detect_hosts.py` notes for same-volume profiles). |
| Anonymised outputs | Before publishing, grep the anonymised `compiled/` tree and any rendered document for host names, user names, e-mails and directory names from the private map (`~/.ai-usage-ledger/anonymize-map.json`); the test suite does this on fixtures, the operator does it on real data. |
| Documents | Every ledger placeholder in a rendered document is filled; a leftover `{name}` is either a `--var` the template needs (recipient, contract, correction values) or a bug. |

## Quality Rules

| Rule | Requirement |
|---|---|
| Read-only | Never modify, delete or "clean up" agent directories; do not `wsl --shutdown` while agents run. |
| Secrets | Decode `id_token` claims for identity; never print or copy tokens or API keys. |
| Evidence classes | Keep class A (per-call records), class B (tool counters) and class C (priced estimates) apart in every table. |
| Confidence | Every finding and every attribution rule carries a confidence level and its evidence. |
| Unknowns | Price unpublished models at a stated sibling marked `assumed`; report the share of cost that rests on them. |
| Corrections | When a rerun changes a previously reported figure, state the cause alongside the new number. |
| Trusted input | `manifest.json`, `config.json`, `accounts.json`, `pricing.json` and `report_config.json` are executable configuration: they name hosts to reach over SSH or WSL and text to render. Keep them owner-writable only (the scripts warn otherwise) and never populate them from untrusted content. |
| No shells | Local commands are argument lists (no `os.system`, no `shell=True`); remote SSH and WSL command words are validated against a strict grammar (`safety.py`) and quoted; the CSV merge sort is Python, not `sort`. |
| Rendering | Branding text is HTML-escaped; colours, theme tokens and fonts are validated; the logo must be a local file (inlined as a data URI); `extra_css` needs `unsafe_extra_css: true` and may not contain `</`, `@import` or `url(`. |
| Private files | The ledger home, store, archive, logs and their files are created owner-only (0700 / 0600 on POSIX; the profile ACL on Windows) and repaired when found otherwise; a config that others can edit is refused unless `AI_USAGE_LEDGER_ALLOW_SHARED=1`. `accounts.json` is copied into a study package only with `package_accounts: true`. |

## Resource Guide

| Resource | Role |
|---|---|
| `references/harness-catalog.md` | Forty-plus agents, IDE assistants, gateways and runtimes: paths per OS, record shapes, token fields, scanner support. |
| `references/log-formats.md` | Exact fields per built-in parser, de-duplication and replay rules, normalised schema. |
| `references/discovery.md` | Where logs and credentials live, sweep commands, reading accounts safely, defensible attribution rules. |
| `references/pitfalls.md` | Seventeen ways the numbers go wrong. |
| `references/harnesses.md` | Install locations and notes for Claude Code, Codex, Cursor, SSH, WSL and macOS. |
| `references/ledger-document-catalog.md` | Fifteen ledger documents (executive summary, monthly statement, quarterly review, account statement, subscription memo and renewal recommendation, cache brief, budget forecast, project allocation, billing evidence, model mix, tool adoption, host inventory, data-quality note, correction notice) with their placeholders. |
| `references/template-index.json` | Machine-readable index of the catalog used by the renderer. |
| `templates/` | Manifest, pricing sheet, account and report-config examples. |
| `examples/` | A workstation manifest and the CompleteTech brand preset. |
| `scripts/ledger.py` | Daily entry point: `init` (onboarding), `run` (scan, append, rebuild), `status`, `export`, `reinit`. |
| `scripts/detect_hosts.py` | OS-aware discovery of harness roots, profiles, drives, WSL distros and credential claims; prints or emits manifest hosts and an accounts draft. |
| `scripts/ledger_store.py` | Append-only store with SQLite, JSON (JSONL) and CSV backends, stable event ids, prefs and run history, exports. |
| `scripts/run_pipeline.py` | One command: scan every host, merge, analyse, render, zip (used by `ledger.py`, also usable alone). |
| `scripts/render_ledger_doc.py` | `--list` the catalog or `--template <id>` to fill it from the ledger: Markdown and themed HTML always, `--pdf`, `--docx`, `--png` when the optional libraries are installed; `--anonymize` reads the anonymised copy. |
| `scripts/render_pdf.py` | Branded Markdown to PDF / DOCX (letterhead band, logo, accent tables, footer). |
| `scripts/anonymize.py` | Salted pseudonyms for hosts, sessions, projects and accounts; paths, prompts and identities removed; private map kept beside the store. |
| `scripts/schedule.py` | Task Scheduler (Windows) or crontab (Linux, WSL, macOS) entry that runs `ledger.py run` daily, weekly or monthly through a wrapper that logs to `~/.ai-usage-ledger/logs/run.log`. |
| `scripts/ledger_archive.py` | Raw-log archive: copies every source file the scanners read (any tool, any host kind) into `~/.ai-usage-ledger/archive/<host>/...`, gzip by default, with an index; `status`, `list`, `grep`, `restore`. |
| `scripts/ledger_query.py` | Question layer: thirty presets (totals, by day / week / month / tool / host / model / project / account / plan / kind / entrypoint / hour / weekday / effort / version, sessions, one session, raw calls, biggest calls, cache, first-last, prompts, prompt counts), free SQL, and regex search inside the archived logs; filters by date range, tool, host, account, model, project, session, kind, plan, billing; table / csv / json / jsonl output. |
| `scripts/compile_ai_logs.py` | `scan` (14 parsers plus a generic sniffer) and `report` (merge, price, attribute). |
| `scripts/analyze_events.py` | Distributions, time of day, concentration, validation, sensitivity. |
| `scripts/build_dashboard.py`, `scripts/build_report.py` | Branded dashboard and study package. |
| `tests/make_fixtures.py` | Synthetic logs and totals check for every parser. |
| `tests/make_onboarding_example.py`, `assets/examples/example-onboarding.md` | The onboarding, question by question, on a synthetic machine; show it to an operator before asking the questions in chat. |
| `tests/test_store.py` | Every backend ingests once and skips the repeat; non-interactive onboarding; two `ledger.py run`s end with zero new rows and archive every source file exactly once; the anonymised copy holds no fixture host, path or e-mail; schedule dry-runs; presets, SQL, prompt search and archived-log search return the expected rows; all fifteen documents render with no ledger placeholder left. |
| `tests/test_security.py` | Shell syntax in the output directory, SSH and WSL manifest fields, the scheduler wrapper and branding stays literal or is refused; generated pages carry a CSP and no external references. |
| `scripts/safety.py` | The validation and escaping helpers the pipeline, renderers and scheduler share. |

## Runtime Permissions

| Capability | Boundary |
|---|---|
| Files read | Agent transcripts, tool databases and credential files under the user's own profiles and hosts named in the manifest; bundled templates, references and `assets/logo.png`. |
| Files written | `~/.ai-usage-ledger/` (or `$AI_USAGE_LEDGER_HOME`): `config.json`, the store, generated `manifest.json`, `accounts.json`, `pricing.json`, `report_config.json`, `anonymize-map.json`, `run-ledger.cmd|sh`, `logs/`, and `archive/` when raw-log archiving is on (size of the tools' log trees, roughly one tenth when compressed); `scans/`, `compiled/`, `store-export/`, `reports/`, `anonymized/` and `documents/` under the chosen `workdir`; `tests/fixtures`, `tests/out` during the test suites. |
| Local commands | `python3` for the scripts; `wsl.exe -l -q` to list distros during detection; `wsl.exe`, `ssh` and `scp` only for hosts in the manifest; `schtasks` or `crontab` only when the operator asks for a scheduled refresh (`schedule install|remove`), never silently. |
| Not required | Outbound network access (pricing pages are fetched by the operator, not the scripts), credential use, persistence, privilege escalation, destructive file operations, background services. |

## Renderer

| Task | Command |
|---|---|
| Onboard (interactive) | `python3 scripts/ledger.py init` |
| Onboard (agent or CI, no prompts) | `python3 scripts/ledger.py init --yes --set brand.name=Acme --set store.kind=sqlite --set detect.all_profiles=y` |
| Refresh everything | `python3 scripts/ledger.py run` |
| Rebuild without rescanning | `python3 scripts/ledger.py run --no-scan` |
| Scan a subset of hosts | `python3 scripts/ledger.py run --hosts lighthouse,wsl-ubuntu` |
| What is configured and stored | `python3 scripts/ledger.py status` |
| Export the store | `python3 scripts/ledger.py export --table events --format csv --out events.csv` (`json`, `jsonl`; tables `events`, `sessions`, `prompts`) |
| Start over | `python3 scripts/ledger.py reinit` |
| Anonymised copy for publication | `python3 scripts/ledger.py run --anonymize` (or `--set anonymize.on_every_run=y` at onboarding); outputs under `<workdir>/anonymized/`; `ledger.py export --anonymize` for tables |
| List ledger documents | `python3 scripts/ledger.py doc --list [--stage finance] [--type memo]` |
| Render a document | `python3 scripts/ledger.py doc --template monthly-usage-statement --var prepared_for="Finance" --var month=2026-08 --pdf --docx` |
| Render from the anonymised copy | `python3 scripts/ledger.py doc --template executive-summary --anonymize --pdf` |
| Scheduled refresh | `python3 scripts/ledger.py schedule install --frequency daily --time 03:00` · `schedule status` · `schedule remove` (`--dry-run` prints the wrapper contents and the command only; the wrapper carries `--anonymize` / `--archive` flags at most, nothing free-form) |
| Raw-log archive | `python3 scripts/ledger.py archive status` · `archive list --host wsl-ubuntu --grep-path 2026/08` · `archive grep "ECONNRESET" --since 2026-08-01` · `archive restore --host lighthouse --to /tmp/restored --match sessions/2026/08` · one-off: `ledger.py run --archive` |
| Detailed questions | `python3 scripts/ledger.py query --presets` · `query totals --since 2026-08-01` · `query by-project --tool codex --since 2026-08-01 --until 2026-08-31 --limit 10` · `query sessions --project libreevolve` · `query session --session <id>` · `query prompts --grep "rate limit"` · `query sql "SELECT ..."` · `query logs "pattern" --since 2026-08-01` |
| Just look at what is on this machine | `python3 scripts/detect_hosts.py --all-profiles` (`--json` for the manifest shape) |
| Manual pipeline (no store) | `python3 scripts/run_pipeline.py --manifest manifest.json [--only report,analyze,build] [--hosts a,b]` |
| Parser, store and security self-tests | `python3 tests/make_fixtures.py` · `python3 tests/test_store.py` · `python3 tests/test_security.py` |
| Quality gate | `python3 scripts/validate_quality.py` |

| Preference key (`--set`) | Values |
|---|---|
| `brand.name`, `brand.eyebrow`, `brand.tagline`, `brand.contact`, `brand.logo`, `brand.accent`, `brand.footer` | Free text; the logo is a local PNG/SVG path, inlined as a data URI (a URL is used only with `allow_external_resources: true`); accent is hex. |
| `theme` | `light`, `dark`, `system` (initial theme of both pages; the viewer's toggle still wins). |
| `store.kind` | `sqlite` (one file, indexed), `json` (JSONL files plus id index), `csv` (CSV files plus id index). |
| `workdir`, `timezone` | Paths and IANA zone. |
| `detect.all_profiles`, `detect.wsl` | `y` / `n`. |
| `anonymize.on_every_run` | `y` / `n`: also build `<workdir>/anonymized/` on every run. |
| `archive.raw_logs`, `archive.compress`, `archive.path` | `y` / `n` keep the raw log files; `y` / `n` gzip them (`n` keeps them re-scannable in place); directory (default `~/.ai-usage-ledger/archive`). |
| `schedule.frequency`, `schedule.time`, `schedule.weekday`, `schedule.install` | `none` / `daily` / `weekly` / `monthly`; `HH:MM`; `mon`..`sun`; `y` installs the task or cron entry during onboarding (ask first). |

| Output | Path |
|---|---|
| Ledger store (source of truth after the first run) | `~/.ai-usage-ledger/ledger.sqlite`, or `ledger-json/`, `ledger-csv/` (tables `events`, `sessions`, `prompts`, `prefs`, `runs`) |
| Event log (primary artefact) | `compiled/all_events.csv` |
| Aggregates | `compiled/by_*.csv`, `subscription_vs_api*.csv`, `SUMMARY.md`, `summary.json`, `analysis.json` |
| Dashboard | `compiled/agent-ledger.html` |
| Study package | `reports/<prefix>_<date>/` (`USAGE_REPORT.md`, `report.html`, `ledger.json`, `pricing.json`, `accounts.json`, `README.md`, `SHA256SUMS`) and `.zip` |

## Branding and Themes

| Element | Source |
|---|---|
| Default | Neutral: the name "Usage Ledger", an accent colour and a footer saying branding has not been configured. No publisher name, contact, logo or slogan appears unless chosen. |
| Brand preset | `examples/report_config.completetech.json`, applied only on explicit request (`init --brand-preset completetech`, the first onboarding prompt, or `--set brand.preset=completetech`): CompleteTech LLC logo, eyebrow, tagline, contact, footer and palette (`#1E3A8A` accent, `#0F172A` ink, `#EEF2FF` soft accent, `#64748B` muted, `#E2E8F0` border, `#F8FAFC` zebra). |
| Logo | `assets/logo.png`, inlined as a data URI so both pages stay self-contained. |
| Themes | Light, dark and system in both pages via `prefers-color-scheme`, a fixed Light / System / Dark toggle persisted in the browser, and an explicit `data-theme` stamp from a host. |
| Overrides | `branding.light` / `branding.dark` may set any token (`bg`, `surface`, `surface-2`, `ink`, `ink-2`, `ink-3`, `line`, `line-2`, tool colours, `seq1..seq7`) to a plain CSS colour or length; `font_display` / `font_body` / `font_mono` name locally installed fonts; `google_fonts_url` is honoured only with `allow_external_resources: true`; `extra_css` only with `unsafe_extra_css: true`. Keep tool colours CVD-safe. |

## Store and De-duplication

| Element | Rule |
|---|---|
| Event id | Tool request id when the tool records one (Claude message id); otherwise SHA-1 of tool, host, session, source file name, timestamp, model, the four token counts and an ordinal among identical keys in that file. Re-scanning an append-only log yields the same ids. |
| Ingest | `INSERT OR IGNORE` (SQLite) or an id index (JSON, CSV). Rows are never updated or deleted; a changed rule is applied at report time, not in the store. |
| Sessions and prompts | Same scheme keyed on tool, host, session and file (sessions) or timestamp, session and text (prompts). |
| Prefs and runs | Every preference is mirrored into the store; each `run` records what it added, skipped and produced. |
| Reinit | Moves the store aside as `<store>.before-reinit-<stamp>` and onboards again; nothing is deleted. |

## Anonymisation

| Element | Rule |
|---|---|
| Replaced | Host names to `host-<6 hex>`, session and request ids to 12-hex digests, working directories to `project-<8 hex>`, account keys to `<tool>:acct-<6 hex>`, any path, URL or e-mail in a free-text field to `path-`/`user-` tokens. |
| Removed | Source file paths, prompts, account labels, e-mails, organisations, evidence strings, host descriptions and the primary-host note in the report config. |
| Kept | Tool, model, plan type, timestamps, token counts, costs, kind, entrypoint kind, version, effort: the study itself. |
| Stability | Pseudonyms are SHA-256 of a private salt generated at onboarding, so reruns agree and outsiders cannot reverse them; the real-to-pseudonym map stays in `~/.ai-usage-ledger/anonymize-map.json`. |
| Branding | The publisher's own branding stays on anonymised outputs; change it at onboarding if the publisher differs from the operator. |

## Raw-Log Archive

| Element | Rule |
|---|---|
| What is kept | Every file a scanner read on the last run (the `src` of each event, the `file` of each session), plus the counters beside the roots (`stats-cache.json`, `state_5.sqlite`, `history.jsonl`, `session-store.db`). Credential files are never archived. |
| Harness-agnostic | The archive follows the scanners' source paths, so a new parser or a generic-root tool is archived without any archive-side change; nothing in the archive knows tool formats. |
| Hosts | Local and share hosts by copy; WSL through the `\\wsl$` share; SSH hosts through fixed remote commands (`xargs -0 stat`, `tar --null -T -`) that read a NUL-delimited file list on stdin after the target passed `safety.validate_ssh_host`; no remote shell script is ever composed from paths. |
| Boundaries | Host names are plain identifiers; every source path (from the scan output, which is data) must be absolute with no control characters and no `..`; every destination is verified to stay inside the archive root after symlink resolution, on archive and on restore. |
| Append-only | A file is copied when new or grown; the tools only append, so the latest copy is a superset. The index keeps a version count and nothing is deleted. |
| Reading back | `archive grep` streams through gzip and reports file, line and the timestamp found on the line; `archive restore` decompresses a host (or a path match) into a directory that the scanners can read again. |
| Size | Expect the size of the tools' log trees (tens of GB for heavy Codex use) at roughly one tenth when compressed. Say so before enabling it on a small disk. |

## Answering Detailed Questions

| Question shape | Command |
|---|---|
| How much on a day / week / month, optionally one tool or host | `query by-day --since D --until D [--tool t] [--host h]`, `by-week`, `by-month`, `totals` |
| Which projects, models, accounts, plans, entry points, effort levels, client versions | `query by-project`, `by-model`, `by-model-month`, `by-account`, `by-account-month`, `by-plan`, `by-entrypoint`, `by-effort`, `by-version` |
| Working pattern | `query by-hour`, `by-weekday`, `by-kind` (main vs sub-agents) |
| Biggest or specific sessions and calls | `query sessions [--project p]`, `session --session <id>`, `biggest-calls`, `calls --since D --until D --limit N` |
| Cache behaviour, first and last use | `query cache`, `first-last` |
| What was asked | `query prompts --grep "text" [--since D]`, `prompt-count` |
| Anything else about the counts | `query sql "SELECT ... FROM events|sessions|prompts"` (read-only; columns are the normalised event schema) |
| What the transcript actually said, errors, tool output | `query logs "regex" [--since D] [--host h] [--project path-fragment]` over the archived raw files (needs `archive.raw_logs`) |
| Output for a document or a spreadsheet | add `--format csv|json|jsonl` |

Accounts in `query` come from the same `accounts.json` rules the report uses (`acct()` / `bill()` SQL functions), so per-account answers agree with the dashboard. JSON and CSV stores are loaded into an in-memory SQLite database, so every preset works on every backend.

## Ledger Documents

| Element | Rule |
|---|---|
| Source of figures | `compiled/summary.json` and `analysis.json` of the configured ledger (or `--compiled <dir>`); nothing is typed in by hand. |
| Recipient facts | `--var prepared_for=`, `reference=`, `notes=`, `contract_id=`, `billing_period=`, correction values. |
| Scopes | `--var month=YYYY-MM`, `--var account=<key>`, `--var project=<directory substring>`; defaults are the latest month, the largest account, the largest project. |
| Formats | Markdown and themed HTML always; PDF (reportlab) and DOCX (python-docx) with `--pdf` / `--docx`; PNG preview with `--png`. |
| Wording | Every document states that figures are API-equivalents at list price and not invoices; the billing evidence template feeds `agentic-invoice-skill`, it does not replace it. |

## Scheduling

| Element | Rule |
|---|---|
| Windows | `schtasks` task "AI Usage Ledger" running `~/.ai-usage-ledger/run-ledger.cmd` daily, weekly (`--weekday`) or monthly (day 1) at `--time`. |
| Linux, WSL, macOS | One crontab line tagged `# ai-usage-ledger` running `run-ledger.sh`; macOS may need Full Disk Access for cron. |
| Logging | Each run appends to `~/.ai-usage-ledger/logs/run.log`; `ledger.py status` shows the entry and the last log lines. |
| Consent | Onboarding asks whether to install; an agent passes `--set schedule.install=y` only after the operator has agreed in chat. `--dry-run` prints the exact command. |

## Definitions

`input_uncached` fresh prompt tokens · `cache_read` served from cache · `cache_write` written to cache (Anthropic, split 5m/1h) · `output` incl. reasoning · `total` = sum. API-equivalent = tokens × list price. Cache saving = same call priced with all prompt tokens uncached, minus actual. Subscription months are counted only when that account made a call. Usage-based calls are real spend and stay out of the subscription comparison.

## Network Boundary

| Boundary | Requirement |
|---|---|
| Local-only runtime | The scripts make no outbound network calls; SSH and WSL are used only for hosts the operator names in the manifest. |
| Generated pages | The dashboard, study and documents are self-contained: no external fonts, images or stylesheets, and a `Content-Security-Policy` meta tag that forbids network loads. A remote logo or Google Fonts stylesheet is used only when `branding.allow_external_resources` is true. |
| Publishing | Dashboards and study packages are published only when the operator asks (Artifacts, files, or a repository). |
| Data | Scanned transcripts and the compiled ledger never leave the operator's machines through this skill. |
