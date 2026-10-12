# Plandex: experimental, scoped self-hosted usage exports

**Status: proposed export integration, not stock Plandex support.** The collector reads `plandex-usage/1`, a narrow proposed server extension. A stock 2.2.1 installation does not produce this export. An upstream integration build and review are prerequisites to deployment. The fixture version `2.2.1+usage-export.1` is a synthetic test label, not a released version. Hosted Plandex collection has not been verified and is not supported by this collector.

## Verified baseline and why no PostgreSQL reader

The audit baseline is `plandex-ai/plandex@e2d772072efadbe41d2946d97d79be55532dbab5`; the latest server release marker at that revision is 2.2.1. The ledger baseline is `e9d5e225a802d8eddcc7e1a2fc72cded6db1437e`.

The public server uses PostgreSQL plus persistent filesystem/git state. However, `app/server/db/data_models.go` exposes branch context/conversation token counters and model-stream lifecycle metadata, not authoritative consumed input/output per provider attempt. `app/server/hooks/hooks.go` makes unregistered hooks no-ops, and the public tree has no registration for the `DidSendModelRequest` accounting hook. The model call paths sometimes substitute estimates when providers omit usage. The CLI's `usage` command consumes credit summaries; those are not a verified self-hosted token export. Do not convert context-window counters, plan totals, credit summaries or planned work into request consumption.

No PostgreSQL table, query, migration, credential discovery or connection is implemented. There is consequently no read-only database account to configure. Do not grant the ledger a database role for this integration. A future database adapter would require a separately verified schema, explicit scope, least-privilege read-only role, parameterized queries and separate remote-access consent.

Source references (pinned):

- [Persistent data models](https://github.com/plandex-ai/plandex/blob/e2d772072efadbe41d2946d97d79be55532dbab5/app/server/db/data_models.go)
- [Public hooks](https://github.com/plandex-ai/plandex/blob/e2d772072efadbe41d2946d97d79be55532dbab5/app/server/hooks/hooks.go)
- [Provider boundary and fallback selection](https://github.com/plandex-ai/plandex/blob/e2d772072efadbe41d2946d97d79be55532dbab5/app/server/model/client.go)
- [Interrupted-call estimation](https://github.com/plandex-ai/plandex/blob/e2d772072efadbe41d2946d97d79be55532dbab5/app/server/model/plan/tell_stream_usage.go)
- [General request accounting](https://github.com/plandex-ai/plandex/blob/e2d772072efadbe41d2946d97d79be55532dbab5/app/server/model/model_request.go)
- [CLI credit reporting](https://github.com/plandex-ai/plandex/blob/e2d772072efadbe41d2946d97d79be55532dbab5/app/cli/cmd/usage.go)
- [Latest server release marker](https://github.com/plandex-ai/plandex/blob/e2d772072efadbe41d2946d97d79be55532dbab5/releases/server)

## Producer contract and deployment modes

The separate upstream proposal adds a standard-library Go exporter at the actual shared streaming HTTP-send boundary, after provider fallback and model selection. Existing plan metadata is propagated in context; it is not looked up by the ledger. A start record is written before a send; a terminal record contains only observed usage, safe metadata and status. Each actual HTTP attempt gets its own opaque ID. Request retries are not collapsed merely because they belong to one step. Provider-internal retries that are not visible at this boundary are not independently measurable.

The exporter defaults off. A patched self-hosted server can explicitly set `PLANDEX_USAGE_EXPORT_CONFIG` to an operator-owned local JSON configuration containing `source_id`, `directory`, `project_ids` and `approved_project_scope: true`. The export directory must already exist and be private (0700 on POSIX); the configuration must be private (0600). The operator, not the collector, supplies approved existing project IDs and access. Each server process writes its own exclusively created `journal-<32 lowercase hex>.jsonl` (0600), flushing complete records. Container installations need an explicitly mounted private export directory; do not grant access to unrelated server volumes.

The proposed writer records its build revision when available. Copy that exact recorded `plandex_version` into the collector's allowlist after verifying the build. A missing/unknown build does not establish compatibility. Only export schema 1 is accepted. Older/hypothetical schemas are coverage gaps, not guessed migrations. No historical backfill is available for executions before export was enabled. Calls without approved project/plan metadata are outside export scope.

Direct OpenAI-compatible/OpenRouter usage can be represented when its semantics are verified. Plandex's pinned LiteLLM 1.72.6 gateway may normalize or synthesize usage and its cache-write inclusion was not verified during this implementation. The proposed producer marks that path `gateway_reported_unverified`; the collector retains its numeric evidence in coverage records but does **not** add it to billable token events. This limitation affects common proxied providers, including Anthropic, Gemini and local-model paths. A successful synthetic multi-provider fixture does not certify live provider compatibility.

## Explicit source discovery and configuration

Copy [the example](../examples/plandex.sources.example.json) to an operator-controlled absolute local path. Replace the source identifier, exact build/version allowlist, approved project IDs and local directory. Leave `approved_project_scope` false until the operator has authorized that scope. The acknowledgement is not a substitute for OS permissions or a multi-user access-control system.

A source may specify `files: ["/absolute/approved-export.jsonl"]`, `directories: ["/absolute/approved-export-directory"]`, or both. Directory discovery is non-recursive and recognizes only the native journal-name pattern. It does not read client homes, `.env`, database configuration, provider credentials, container inventories, arbitrary server logs or remote services. A shared export must be readable by the operator; the collector filters records but is not a security boundary for someone who already has access to the raw file. Prefer producer-side scope isolation and separate export directories.

```bash
python scripts/collect_plandex.py --config /absolute/plandex-sources.json --discover
python scripts/collect_plandex.py --config /absolute/plandex-sources.json \
  --out-dir /absolute/private-plandex-checkpoint \
  --store-kind sqlite --store-path /absolute/approved-ledger.sqlite
```

Use the actual configured ledger destination, not a Plandex database. JSON and CSV ledger stores are supported with `--store-kind json|csv` and their corresponding directory path. Omitting both store options emits a private normalized snapshot without opening any ledger store. Paths must be absolute/local, exports and outputs disjoint, and sources regular files, not symlinks, hardlinks or FIFOs. URLs and UNC paths are rejected. Copying a remote export is a separate operator-approved activity; this command performs no network access and has no remote discovery option.

`collect_plandex.py` is a dedicated explicit command; it is **not** automatic `detect_hosts.py` discovery or a new default `ledger.py run` scan. Following ingestion into an already configured ledger, use its normal commands:

```bash
python scripts/ledger.py query totals --tool plandex
python scripts/ledger.py query by-project --tool plandex
python scripts/ledger.py query by-model --tool plandex
python scripts/ledger.py run --no-scan
python scripts/ledger.py report --since 2026-10-12 --until 2026-10-12 --tz UTC
```

The last example is a bounded date example, not an instruction to widen an existing report scope. Existing pricing snapshots, attribution rules and dashboard/report workflows remain authoritative for ledger-side estimates. There is no new dashboard or billing engine.

## Source format and normalization

Each complete UTF-8 JSONL record declares `schema: "plandex-usage/1"`, source/version, project/plan, provider/model, timestamp and native `attempt_id`. Terminal records use `kind: "attempt"`, `granularity: "attempt"` and status `completed`, `error`, `cancelled` or `interrupted`. `attempt_start` only establishes coverage; tool executions and plan/session aggregates never become usage events.

| Export evidence | Ledger representation |
|---|---|
| `usage.input_tokens` | Inclusive input; subtract reported cache-read and cache-write to obtain `input_uncached` |
| `usage.output_tokens` | `output`, including reasoning when the declared semantics say so |
| `usage.cache_read_tokens`, `cache_write_tokens` | `cache_read`, `cache_write`; never subtracted twice |
| `usage.reasoning_tokens` | `reasoning` subset of output; never added again to `total` |
| Native provider/model and version | `provider`, `model`, `version`; no identity inferred from a credential |
| Source + attempt ID | Stable opaque `host` and `request_id`, independent of file location or scan window |
| Project / plan / execution / step / session IDs | Stable pseudonyms; project in `cwd`, session in `session`, others in `plandex_*` extras |
| Timestamp | UTC `ts`/`date`, original in `plandex_native_timestamp` |
| `native_cost` | Decimal string, currency and provenance in `plandex_native_cost`, never `cost_usd` |
| Native token values | Nullable `plandex_native_tokens` and allowlisted `plandex_raw_usage` |
| Evidence | Schema and record SHA-256; no raw prompt/response retained |

The existing ledger `plan` field means billing plan; Plandex plan IDs are deliberately not put there. The provider denotes the observed selected provider/gateway, not an inferred backend organization. No user email, organization name, prompt, response, API key, request body or arbitrary source field is persisted. Opaque IDs use source-separated SHA-256, which is pseudonymization, not proof of anonymity. Retain the existing publication/anonymization review; do not publish the operator configuration or original source exports.

`total = input_tokens + output_tokens`; reasoning is included in output. Missing required input/output yields coverage-only records with available counters preserved. Unknown optional cache/reasoning fields remain null in the native evidence; legacy numeric buckets use zero only for arithmetic. Unsplit input is priced at the ordinary input rate, **not** reported as measured cache-zero. Missing cache-write TTLs cannot establish a precise TTL price; the existing ledger's default/fallback rate applies. Review the coverage sidecar alongside reports, because existing dashboards do not automatically present these Plandex-specific gaps.

Only `provider_reported` with `inclusive_input_output` semantics is admitted as token consumption. Estimates, unsupported semantics and unverified gateway counts remain coverage-only. Negative, noninteger, oversized or inconsistent counters are rejected without inventing replacements. A call may still contain billable observed usage despite an error or cancellation. A zero-token provider response is distinct from unavailable usage.

Native Plandex/provider money and ledger API-equivalent prices are separate. Native amounts never override list-price computation. OpenRouter's returned cost is USD-denominated credit evidence, not independently reconciled invoice data; no purchase fees, BYOK fees or unseen provider charges are inferred. Unrecognized models remain unpriced under existing reporting, rather than free. Exact provider/model prices and any model alias assumptions belong in the approved ledger pricing snapshot.

Provider references: [OpenRouter usage fields](https://github.com/OpenRouterTeam/docs/blob/main/cookbook/administration/usage-accounting.mdx), [cache fields](https://openrouter.ai/docs/guides/best-practices/prompt-caching), [USD credit system](https://openrouter.ai/support/). These references are not a guarantee about every historical gateway version.

## Incremental collection, retries and coverage

The private collector-owned `checkpoint.sqlite` stores offsets, prefix hashes, immutable attempt identities, normalized events and sanitized gaps. It never opens the Plandex database. Existing prefixes are re-read for integrity verification; only appended complete lines are parsed. Thus parsing is incremental, but integrity checking still performs I/O over previously scanned bytes. Rotation or truncation triggers revalidation; duplicate IDs deduplicate, while a conflicting terminal record fails instead of silently changing consumed tokens.

Every scan emits the full cached normalized snapshot. The existing ledger's stable request-ID ingestion skips repeats. This deliberate replay protects the gap between checkpointing and downstream ingestion. SQLite is the preferred durable ledger destination; JSON/CSV retain their existing file/index durability limits. This integration does not promise cross-process crash-proof exactly-once behavior beyond each backend's guarantees.

A growing plan produces new attempts, not revised plan totals. Repeated usage snapshots within one provider stream are not summed by the proposed writer. Aggregates are excluded even when detailed events are present. Starts without terminal records remain unfinished coverage, never fabricated zero usage. Incomplete trailing JSONL is retried on the next scan. Malformed complete records, unsupported versions, missing usage/pricing and unsafe/unavailable paths are visible in receipts. Changing approved scope or file configuration requires a fresh checkpoint directory; keep the same ledger store to retain stable deduplication.

Outputs are `events.plandex.jsonl`, `coverage.json`, `coverage-records.jsonl` and the private checkpoint. Events intentionally have `src: null`, so enabling the existing raw-log archive cannot accidentally copy a multi-user source export. Retain original exports separately under the operator's policy when audit access is required. No local process can reconstruct calls lost before export was enabled, after a process crash before observation, or when the writer could not persist evidence; do not claim complete historical consumption.

## Validation and disabling

Run the synthetic suites from a complete checkout:

```bash
python -m unittest discover -s tests -p 'test_plandex*.py' -v
python scripts/validate_quality.py
python scripts/validate_package.py
```

The committed fixture contains two model attempts emitted by the proposed Go writer. Native store/report tests expect 2 events and 2,200 total tokens, a repeat adds 0, then one new attempt adds exactly 1 event for 3,300 total tokens. They use hypothetical price rows and compare the actual ledger's normalized buckets, native cost separation, provider/model/project attribution and HTML report totals. The tests use only temporary local sources and destinations; they do not require PostgreSQL.

Before real use, separately compile/test the upstream integration, inspect its approved project boundaries, validate an operator-approved sample against the provider evidence, inspect every coverage gap, and repeat collection without activity. Verify only additional attempts enter the store. Required CI, independent review and protected merge rules still apply.

To disable future collection, stop invoking this explicit command. No schedule is installed. To disable future production, unset `PLANDEX_USAGE_EXPORT_CONFIG` and restart the self-hosted server through its normal approved process. Existing export files and ledger events remain; this command does not delete or retroactively anonymize them. Do not delete/recreate the user's store to disable one collector.
