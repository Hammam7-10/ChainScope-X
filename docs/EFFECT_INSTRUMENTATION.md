# R2 Effect Instrumentation

## Shared path

Trusted tools receive a `SandboxContext` containing their R1 manifest permissions, resource allowlist, destination allowlist, execution/invocation identity, and the local adapters. They do not receive the recorder or evidence store directly. Asset reads, database searches, transformations, workspace reads/creates/writes, and simulated transmissions all pass through adapter `_perform` paths. The adapters perform the deterministic operation and report its result to the one shared `EffectRecorder`; tool code cannot independently append an observed event through its context.

Successful operations are recorded only after their operation callback succeeds. A controlled operation failure records a `FAILED` event with a stable reason code when the recorder remains available, then returns failure to the runner. Workspace creation/write and simulated delivery stage in-memory mutation, record success, and roll back the staged mutation if success recording fails. The runner marks the invocation failed, saves safe failure evidence when possible, and marks coverage `FAILED`; it does not return a successful result or allow a complete trace to be claimed.

## Event and evidence provenance

Events use the unchanged R1 `ObservedEffect` model and R1 enum values. A per-execution counter supplies unambiguous 1-based sequence numbers. Timestamps are generated in UTC and are timezone-aware. The event's single `EvidenceReference` resolves to an actual record in the local `EvidenceStore`; no evidence URLs are fabricated. The record contains a canonical, sorted JSON representation of sanitized event facts and its SHA-256 digest. `EvidenceStore.verify` recalculates the digest and checks the reference ID, kind, time, and digest. The digest binds this local test record; it is not a cryptographic proof that an operation happened outside the process.

Evidence excludes document/file contents, query text, raw tool inputs, secrets, and arbitrary free-form metadata. Event metadata keys are allowlisted, string values must match a bounded identifier pattern, lists are limited to safe identifiers, and numeric fields are counts. Operation outcomes, stable synthetic resource IDs, classification, and source/destination IDs remain available for later analysis.

## Coverage calculation

Coverage is an R1 `CoverageRecord` with an explicit, bounded scope over the seven adapter interfaces in `app/sandbox/resources.py`: asset read, synthetic database search, deterministic report transformation, controlled workspace create/read/write, and simulated destination transmit. The recorder self-check creates local evidence before tool work. At finish, `COMPLETE` is allowed only when a nonempty explicit scope exists, the self-check reference verifies, all recorded event evidence resolves, the recorder remains active, and no known gap/failure was recorded. This claims no operating-system-wide or arbitrary-software visibility.

| R1 status | R2 condition |
|---|---|
| `COMPLETE` | Explicit nonempty known interface scope, verified active recorder self-check and all event evidence, no recorded gap |
| `PARTIAL` | A known scope gap is supplied/detected, or the declared scope contains an unrecognized interface |
| `FAILED` | Recorder is inactive, self-check/event evidence integrity cannot be established, or recorder failure occurs during a controlled operation |
| `UNKNOWN` | No explicit usable scope was supplied and coverage cannot be established |

A missing event with `PARTIAL`, `FAILED`, or `UNKNOWN` coverage is not evidence of safety. A normal resource precondition failure may still yield `COMPLETE` coverage because the attempted operation itself was captured as a `FAILED` effect and no instrumentation gap occurred.

## Adversarial fixture

With the `adversarial_storage_external_copy` execution option, the `workspace-storage` tool first performs its ordinary internal read/write and then calls the local `SimulatedDestinationStore` for one additional copy to `destination:external:simulated`. The shared adapter records `TRANSMITS` with the destination and source classification. The exception is narrowly bound to that fixture flag, the `workspace-storage` tool ID, and the fixed simulated external destination. No socket, network request, or real external transmission exists. R2 preserves the declared manifest separately and makes no mismatch judgment.

## Running the tests

```bash
python3 -m unittest tests.test_tool_lab -v
python3 -m unittest discover -s tests -v
```

The R2 tests inject recorder failure at the `WRITES` boundary to verify fail-closed behavior and rollback. The failure hook is deterministic test instrumentation, not an operational bypass.
