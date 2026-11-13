# Domain Model (R1)

## Bounded purpose
ChainScope X analyzes effects recorded by a controlled, declared instrumentation boundary. It does not monitor every operating-system, network, or external effect. Tool descriptions and LLM text are claims/context, not observed facts.

## Core entities

| Entity | Meaning | Identity / invariants |
|---|---|---|
| Tool | Registered executable capability under a versioned manifest. | `tool_id` stable; version, input/output schemas, declared capabilities, declared effects, permission scope, allowed resources/destinations, status. |
| Declared capability | Claim that an operation is supported, e.g. `read_document`. | Not permission. A policy/permission scope separately decides where or whether it is allowed. |
| Declared effect | Manifest-level expected effect class. | Compared to observed event facts; declaration alone is never proof execution occurred. |
| Tool invocation | One call of a registered tool within an execution. | `invocation_id`, `execution_id`, `tool_id`, input/output references, start/end, outcome. |
| Observed effect | Structured instrumentation event from an actual controlled invocation. | Unique event ID, execution/invocation/tool IDs, per-execution sequence, UTC timestamp, effect, resources, classification, outcome, evidence. |
| Effect mismatch | Comparison between a manifest expectation and recorded events. | Kinds: undeclared observed, expected-not-observed, unexpected resource/destination, unexpected operation, incomplete comparison. Missing effects alone are not proof of misconduct. |
| Capability path | Ordered connected graph edges from an asset/source through recorded operations to a destination. | Every edge references observed event IDs and one execution; no edges inferred only from prose. |
| Policy rule | Versioned machine-readable condition and deterministic expected outcome. | Scoped, effective-dated, active/inactive, with explicit evidence requirements. |
| Finding | Assessment linked to event/path, policy when a violation is confirmed, coverage and uncertainty. | Finding type and assessment are distinct: mismatch, potential risk, confirmed violation, inconclusive, or bounded no-violation-observed. |
| Remediation candidate | Proposed constraint and testable expected effects. | Target, type, blocked path, benign workflows to preserve, verification criteria. |
| Verification run | Recorded post-control execution and results. | Must contain run IDs, outcomes, and evidence. Proposal is not success. |
| Coverage record | Instrumentation coverage for a specific execution and explicit declared scope. | COMPLETE is bounded to tested scope only; gaps and recorder identity/version retained. |

## Declaration, permission, observation
A capability is what a tool claims it can do. A permission is what the governing configuration permits in a scope. An observed effect is what instrumented execution recorded. These are independent dimensions: a tool may declare an effect yet lack permission, or cause an undeclared observed effect. A detected mismatch is not automatically a policy violation.

## Assessment and evidence language
- **CONFIRMED_VIOLATION:** deterministic rule applies and a supporting event-backed path demonstrates its prohibited condition.
- **EFFECT_MISMATCH:** declaration and observation differ; policy breach is not implied.
- **POTENTIAL_RISK:** plausible concern without sufficient proof of a prohibited observed path.
- **INCONCLUSIVE:** coverage/evidence cannot support a reliable negative conclusion.
- **NO_VIOLATION_OBSERVED:** no rule violation observed under COMPLETE coverage of the explicitly stated/tested scope; never a universal safety claim.

An observed prohibited event can prove a positive violation even if other coverage is partial, provided the event, path, active policy and applicability are traceable. Conversely, missing an event in PARTIAL/FAILED/UNKNOWN coverage cannot prove safety.

## Data classification
Order: PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED. A transformation combining inputs inherits the maximum sensitivity. Lowering sensitivity is prohibited unless a separate explicit, tested declassification rule with provenance is later designed. LLMs cannot declassify data.

## Evidence provenance
Evidence references identify the recorder/fixture/artifact and may carry a SHA-256 digest. Event IDs are immutable within an execution; append-only creation and integrity checking are the intended design. LLM-generated explanations are not event sources or authoritative evidence. Raw sensitive payloads should not be copied into evidence metadata by default; use access-controlled references/digests.
