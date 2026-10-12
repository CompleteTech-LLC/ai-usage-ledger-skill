# OpenHands SDK token tracking

This opt-in adapter converts **observed native SDK LLM request usage** into the
ledger's existing scanner event schema. It does not add an agent controller,
telemetry service, billing database, dashboard, provider dependency, or background
process. Normal ledger storage, queries, pricing and reports remain authoritative.

## Compatibility and discovery record

Reviewed on 2026-10-12 against:

- Ledger `e9d5e225a802d8eddcc7e1a2fc72cded6db1437e`.
- OpenHands SDK `acca181af1f353975965bcf6486e1d0a58f444c0`.

This is a **source-shape compatibility target**, not a promise that every past or
future SDK release has the same behavior. Recheck these sources when upgrading:

| SDK source | Integration consequence |
|---|---|
| [Metrics / TokenUsage](https://github.com/OpenHands/software-agent-sdk/blob/acca181af1f353975965bcf6486e1d0a58f444c0/openhands-sdk/openhands/sdk/llm/utils/metrics.py) | `Metrics.token_usages` contains request records; `accumulated_token_usage` is a reconciliation counter, not another call. `TokenUsage` has `response_id` but no timestamp. |
| [Telemetry](https://github.com/OpenHands/software-agent-sdk/blob/acca181af1f353975965bcf6486e1d0a58f444c0/openhands-sdk/openhands/sdk/llm/utils/telemetry.py) | Normalizes LiteLLM Chat Completions and Responses usage. Completion logs include final response usage, completion timestamp and SDK cost. Missing usage is not zero usage. |
| [ConversationStats](https://github.com/OpenHands/software-agent-sdk/blob/acca181af1f353975965bcf6486e1d0a58f444c0/openhands-sdk/openhands/sdk/conversation/conversation_stats.py) | `usage_to_metrics` separates agent, condenser and other usage slots. `get_combined_metrics()` must not be added to its members. Snapshot serialization can omit histories. |
| [LLMRegistry](https://github.com/OpenHands/software-agent-sdk/blob/acca181af1f353975965bcf6486e1d0a58f444c0/openhands-sdk/openhands/sdk/llm/llm_registry.py) | The public `usage_to_llm` view exposes each LLM's metrics; reading it needs no replacement subscriber. |
| [LLMCompletionLogEvent](https://github.com/OpenHands/software-agent-sdk/blob/acca181af1f353975965bcf6486e1d0a58f444c0/openhands-sdk/openhands/sdk/event/llm_completion_log.py) | Existing remote log events carry JSON in `log_data` and a `usage_id`. The importer projects usage without retaining the transcript. |

The existing harness catalog has dedicated and generic parsers for other tools;
OpenHands is deliberately **not** routed through the generic recursive usage
sniffer. SDK totals, gateway totals, nested raw responses and copied histories
would otherwise look like independent calls. The SDK's open prompt-composition
PR [#4623](https://github.com/OpenHands/software-agent-sdk/pull/4623) estimates
composition offline; those estimates are not inputs to this adapter.

The SDK already exposes sync/async LLM execution, telemetry and conversation
statistics. No upstream patch or callback replacement is needed for this adapter.
`Telemetry.set_stats_update_callback` and the registry's subscriber are single
slots used by SDK/server behavior; this integration does not overwrite them.

## Accepted evidence

`scripts/openhands_usage.py` accepts explicitly selected JSON files only:

**Full native statistics:** either `{"usage_to_metrics": {...}}` or a persisted
state containing `stats.usage_to_metrics`. Each group must contain its full
`token_usages` list. Include historical agent, condenser and delegate groups.
Do not supply `Metrics.diff()` slices as if they were full histories. Available
accumulated counters are checked against the unique request records; discrepancies
are reported and never converted to guessed extra requests.

**Existing SDK completion logs:** Telemetry's JSON object containing `timestamp`,
`latency_sec`, and a final `response` with `object: "chat.completion"` or
`object: "response"`. Serialized `LLMCompletionLogEvent` wrappers are also accepted.
The response's usage is authoritative over `usage_summary` or `raw_response`;
neither is counted again. Streaming chunks and action/tool events are not calls.
An incomplete/failed final response that reports usage still contributes those
actual counts. An error without provider usage contributes an explicit coverage
exclusion, not a zero-token row.

Core input/output counts must be nonnegative integers. Booleans, strings, fractional
values, non-finite values, conflicting aliases, inconsistent totals, and cache or
reasoning subsets exceeding their parent count are rejected. The adapter bounds
counts to the exact integer range supported by the existing store's float-based
round-trip conversion. No tokenizer, content-length heuristic, cost-to-token
conversion, context-window counter or quota counter is used.

For native LiteLLM usage:

```text
input_uncached = prompt_tokens - cache_read_tokens - cache_write_tokens
output        = completion_tokens                  # includes reasoning
reasoning     = reasoning_tokens                   # subset, not extra output
total         = input_uncached + cache_read + cache_write + output
```

Responses API `input_tokens` / `output_tokens` are mapped to the same buckets.
Missing optional provider detail fields normalize to zero **with their names
preserved in `unreported_token_fields`**; zero is not asserted to be provider-reported.
Metrics histories already contain SDK defaults, so they cannot recover whether a
provider originally omitted an optional field. `usage_evidence` distinguishes
provider-response records from these SDK-normalized records.

No cache-write time-to-live is invented. Aggregate cache-write tokens are retained;
TTL-specific columns are left absent. `cache_write_ttl` and the coverage file flag
that limitation. The existing pricer's aggregate-cache-write fallback uses its
short-duration rate; treat that part of the API-equivalent estimate as uncertain
when the actual duration is unknown. SDK-reported dollars are kept only in
`sdk_reported_cost_usd`, with an explicit unverified-evidence label. They do not
populate `cost_usd` or override configured ledger pricing: SDK cost can be calculated,
and the SDK writes zero when cost is unavailable. Provider invoices remain the
source of truth for billing. Unknown models remain unpriced in scoped reports;
this adapter adds no model-family price fallback.

## Import existing, approved files

Read the normal [onboarding and consent boundaries](../ONBOARDING.md) first. This
command neither initializes the ledger nor searches home directories. Supply the
actual conversation ID and a stable execution-host label. The new output
directory's parent must already exist.

```bash
python scripts/openhands_usage.py \
  --completion-log /approved/conversation/request.json \
  --stats /approved/conversation/base_state.json \
  --host runner-a --conversation-id CONVERSATION_ID \
  --out-dir ./openhands-export-001
```

Both input flags are repeatable; all files in one invocation belong to the declared
conversation. Import separate conversations separately. Prefer completion logs
first and reconcile them with full histories in the **same batch**, before the
append-only store is updated. `events.openhands.jsonl` contains only normalized
usage and attribution metadata. `openhands-coverage.json` records exclusions,
reconciliation discrepancies, duplicate counts and undated records. It intentionally
is not named `inventory.*.json`, which belongs to the compiler's different schema.

Exit codes: `0` means no known exclusions in the supplied evidence; `2` means the
export was written but has coverage exclusions; `1` means a fatal conflict or output
failure. `--allow-partial` changes exit code 2 to 0 but **does not remove the partial
flag or diagnostics**. Conflicting usage for the same response ID aborts before any
export is written. Inspect coverage even on exit 0: it is not proof of complete
provider billing, and undated events are reported separately from usage exclusions.

Feed the event file into the **existing configured store**. The example below uses
SQLite; replace both kind and path with the values from your ledger configuration.
The store CLI also supports `json` and `csv`. Do not run a second writer concurrently.

```bash
python scripts/ledger_store.py --kind sqlite --path /approved/ledger/store.sqlite \
  ingest ./openhands-export-001/events.openhands.jsonl

python scripts/ledger.py query totals --tool openhands-sdk
python scripts/ledger.py run --no-scan
python scripts/ledger.py report --since today --tz America/New_York
```

The `ledger.py` commands use the configured store; using a different path in the
ingestion command will not update it. The standalone query CLI supports explicit
store selection for validation:

```bash
python scripts/ledger_query.py totals --tool openhands-sdk \
  --store-kind sqlite --store-path /approved/ledger/store.sqlite --format json
```

Unfiltered queries include undated metrics records. Time-scoped reports exclude
records without usable timestamps and expose that limitation; they do not assign
the import time, file modification time, cost-list timestamp or conversation end
time to historical calls. Legacy `logged_cost_usd` query totals are not a measurement
of OpenHands billed dollars; use the priced reports and the qualified SDK cost extra.

## Opt-in capture from an existing Python execution

Add the ledger's `scripts` directory to your application's import path. Call the
helper only when the conversation is quiescent, after `run()` / `arun()` completes,
pauses, or fails. It does not start an agent, enable logs, replace callbacks, reset
metrics, or send data anywhere.

```python
from pathlib import Path
from openhands_usage import collect_conversation, write_batch

# Existing application creates, owns and runs `conversation`.
# Capture at its existing post-run boundary (also on its error/pause path).
usage = collect_conversation(conversation, host="runner-a")
write_batch(usage, Path("./openhands-export-002"))
```

Use the application's error handling so an export failure does not mask an agent
failure. Each export directory must be new. Capture after every completed run and
again before disposal as appropriate; replayed requests are deduplicated by the
store. Export before replacing or disposing of an LLM whose history is not retained
by conversation statistics. The helper reads `conversation.conversation_stats` and
public `conversation.llm_registry.usage_to_llm` when available, and projects only
metric fields rather than serializing LLM configuration or the whole conversation.

No SDK dependency is installed by the ledger. No periodic task, external service,
callback subscription or completion logging is enabled. Existing completion logs
may contain sensitive prompts and configuration: only select approved files. The
adapter parses them in memory but exports no messages, completions, tool arguments,
raw response bodies, tracebacks, authorization headers or credential fields.
Explicit source paths and request/conversation/model identifiers are retained as
metadata. POSIX exports use directory mode 0700 and file mode 0600; use an
ACL-restricted parent directory on Windows. Existing output directories are refused.

## Identity, coverage and known upstream limitations

The event `request_id` hashes `(namespace, response_id)`; the existing store also
keys it by tool and host. It is independent of source filename, snapshot order,
usage slot and conversation ID. This prevents repeated snapshots, multiple actions
from one response, delegate roll-ups and resumed/forked histories from multiplying
usage. Different response IDs with identical token counts are still different calls.
All observing sessions/usage slots are retained as extras; `session` is the first
observed attribution, not a claim that a shared call was executed twice. Model names
come from individual request records, not the current agent configuration;
`model_aliases` preserves differing names observed for a shared response.

Response IDs must be unique within an execution host and namespace. Use
`--namespace` to distinguish independent provider/proxy installations that reuse
IDs, but keep it identical for overlapping sources. Records without a usable
response ID are explicitly excluded rather than assigned a guessed identity. They
need a source with stable request IDs before idempotent import. Do not import the
same calls through a legacy generic parser under another tool name as well.

The underlying ledger is append-only: a later import does not enrich or correct an
already stored event. Choose the richest evidence before the first ingestion. A
corrected provider record or later-discovered timestamp requires an explicit
operator reconciliation; this adapter does not silently rewrite history.

Upstream issues reviewed as limitations, not fixes delivered by this integration:

- [#5647](https://github.com/OpenHands/software-agent-sdk/issues/5647): continued
  `/v1/chat/completions` can report conversation-total usage. Gateway API usage is
  not accepted as native per-LLM-call evidence.
- [#5639](https://github.com/OpenHands/software-agent-sdk/issues/5639): a model
  switched before first run can be absent from conversation statistics. Local
  capture also reads the public registry; a state file alone cannot recover an
  omitted group.
- [#5561](https://github.com/OpenHands/software-agent-sdk/issues/5561): persisted
  and fetched state may lag live nested metrics. Snapshot files are not proof of
  an in-flight conversation's latest usage.
- [#5687](https://github.com/OpenHands/software-agent-sdk/issues/5687): ACP usage
  semantics differ from native request metrics. ACP turn summaries/context-fill
  counters are out of scope and must not be supplied as native statistics. Known
  ACP state/agent objects are explicitly rejected. A stats-only document has no
  agent-type discriminator, so its producer must establish native-LLM provenance.

Telemetry can omit a zero-token metrics row or have no usage after a transport
failure/cancellation. Latencies without token records are surfaced as unknown
usage; costs and counters never manufacture missing requests. Snapshots without
histories, invalid records and counter/history mismatches remain visible. This
adapter reports available evidence, not unobservable provider attempts.

## Validation

Synthetic fixtures are constructed in the tests; none come from personal logs.

```bash
python -m unittest discover -s tests -p 'test_openhands_*.py' -v
python -m unittest discover -s tests -p 'test_package_*.py' -v
python scripts/validate_package.py
python scripts/validate_quality.py
```

The new additive GitHub workflow runs the OpenHands tests on Python 3.12 and 3.13.
Existing package and Quality gates remain unchanged. Contracts cover normalization,
stream/failure handling, missing evidence, cache/reasoning accounting, model changes,
public-registry capture, duplicate/conflicting snapshots, privacy, bounded input,
output permissions and concurrency, plus real SQLite/JSON/CSV store replay,
query/export, the shared pricer and timezone-scoped reports. No upstream SDK tests
or live provider calls are implied by these ledger-side contracts.
