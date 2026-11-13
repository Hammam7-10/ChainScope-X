# R2 Controlled Tool Laboratory

## Purpose and boundary

R2 is a deterministic, process-local laboratory for six trusted synthetic tools. It is not the ChainScope X application runtime, an operating-system sandbox, or a general plugin host. All tool work is limited to explicit Python adapters backed by in-memory fixtures. The tools do not use subprocesses, shell commands, filesystem APIs, network sockets, a live database, Supabase, or external services. Simulated external delivery is an in-memory record only.

The R1 Pydantic `ToolManifest`, `ObservedEffect`, `EvidenceReference`, `CoverageRecord`, `EffectType`, `Classification`, and `CoverageStatus` remain the contract source. R2 adds no fields or enum values to the R1 contracts or exported JSON Schemas. Observed operation names use the exact R1 effect types: `READS`, `SEARCHES`, `TRANSFORMS`, `CREATES`, `WRITES`, and `TRANSMITS`.

## Static tool registry

`app/tools/registry.py` stores an R1 manifest, implementation object, and Python implementation reference for each approved tool. Registration revalidates the manifest, rejects duplicate IDs, and checks the implementation's exact class against a six-class allowlist. Unknown IDs fail with `UNKNOWN_TOOL`. Only the small declared JSON-schema subset is validated; there is no dynamic Python loading or external code execution. The registry returns manifest copies for listing and lookup.

| Tool ID | Actual controlled work | Declared R1 effects |
|---|---|---|
| `document-reader` | Reads a registered synthetic asset, optionally selecting known fields | `READS` |
| `database-search` | Case-insensitive substring search over the local fixture rows, respecting `limit` | `SEARCHES` |
| `data-transformer` | Reads one or more assets, makes a deterministic report, then creates an internal file object | `READS`, `TRANSFORMS`, `CREATES` |
| `file-creator` | Reads an asset and creates a validated file-like object in the internal workspace | `READS`, `CREATES` |
| `workspace-storage` | Reads a workspace file and stores a copy in the internal reports folder | `READS`, `WRITES` |
| `file-sharing` | Reads a workspace file and records a simulated delivery to an allowlisted destination | `READS`, `TRANSMITS` |

The deliberate R2 adversarial fixture adds an observed `TRANSMITS` event to `workspace-storage` only when its explicit execution fixture option is enabled. The normal declared manifest remains separate and declares internal read/write behavior only. R2 records this difference; it does not label it malicious or analyze the mismatch.

## Execution lifecycle

`LabRunner.start_execution(scope)` creates a unique execution ID, records a bounded scope self-check when scope is explicit, and accepts a fixture option for the adversarial storage test. Each `invoke(execution_id, tool_id, input)` makes a unique invocation ID, validates input against the manifest, constructs a permission-bounded `SandboxContext`, and invokes the approved implementation. `finish_execution` returns execution/invocation records, ordered observed effects, and an R1 `CoverageRecord`.

Every observed event retains the R1-required event, execution, invocation, and tool IDs; sequence; timezone-aware timestamp; effect type; source/destination identities where applicable; classification; operation; outcome; evidence reference; and allowlisted metadata. Sequence values increase monotonically within an execution.

## Running a deterministic example

From the project root:

```python
from app.sandbox.runner import LabRunner, default_monitored_scope

lab = LabRunner()
execution_id = lab.start_execution(default_monitored_scope())
created = lab.invoke(execution_id, "file-creator", {
    "asset_id": "asset:confidential:case-7",
    "filename": "case-summary.json",
})
stored = lab.invoke(execution_id, "workspace-storage", {
    "file_id": created["output"]["file_id"],
})
report = lab.finish_execution(execution_id)
assert report.coverage.status.value == "COMPLETE"
```

Use `adversarial_storage_external_copy=True` in `start_execution` to reproduce the controlled extra-copy scenario. Each new `LabRunner` instance starts with a fresh deterministic fixture set. Runtime data and evidence disappear with the process; there is no persistence claim.

## Known limits

No user-facing API endpoint, dashboard, persistent execution store, PostgreSQL integration, policy evaluation, graph construction, mismatch detection, finding, remediation, RAG, LLM, or third-party tool execution is part of R2. The registry supports only the specified static JSON-schema subset. Python's object model is not presented as a hostile-code security sandbox; safety derives from executing only these audited trusted implementations through narrow adapters. R2's `COMPLETE` means complete observation only for an explicit, tested in-lab interface scope.
