# Capability Graph Specification (R1)

## Graph model
Directed multigraph scoped to one or more executions. A graph node has stable `node_id`, typed as TOOL, ASSET, TRANSFORMATION, DESTINATION, POLICY, or EXECUTION. Node resource IDs identify the referenced registered object; execution linkage is required for run-specific nodes. A relationship is a directed edge with unique `edge_id`, source/target IDs, effect-derived type, `execution_id`, supporting `event_ids`, evidence IDs, and classification.

Supported edge types map to observed effect types: READS, SEARCHES, TRANSFORMS, CREATES, WRITES, TRANSMITS, DELEGATES, and REQUIRES_APPROVAL. Direction represents data/control movement as recorded, not merely a tool association. An edge is invalid if endpoints do not exist, event IDs do not exist, or any event belongs to another execution/tool invocation inconsistent with the edge.

## Path semantics
A path is an ordered sequence `node_0 -> edge_0 -> node_1 ... -> node_n` with `n >= 1`; every edge endpoint must match its adjacent nodes. The path records the execution ID, event IDs, source classification and destination. The path's classification is the conservative maximum of all contributing input labels. Path extraction is deterministic (stable ID/order tie-breaking), bounded by configured depth and returns evidence IDs for every step.

Reachability is a graph property only. Reachability alone is not a violation: a deterministic, active, applicable policy must prohibit the demonstrated destination/operation/classification, and the finding must reference the path and its source events. Descriptions, declared capabilities, or presumed connections do not create edges.

## Coverage
Each execution associates one coverage record. A path established by positive trustworthy events can support a finding even if other scope is unmonitored. Absence of a path under PARTIAL, FAILED, or UNKNOWN coverage cannot imply safety. Report the coverage status and specific gaps alongside the result. COMPLETE applies only to its enumerated, tested scope and recorder version.

## Proposed graph contracts
The R1 Pydantic contracts specify node, edge, and path shape. Referential integrity, same-execution consistency, edge continuity and deterministic traversal are requirements for R4 implementation and are not falsely claimed as implemented here.

## Example (illustrative only)
`ASSET confidential:case-7 --READS(event-11)--> TOOL reader --TRANSFORMS(event-12)--> TOOL reporter --TRANSMITS(event-13)--> DESTINATION sink:external`
A finding is confirmed only if those events exist in one linked execution, provenance is trustworthy, an effective rule applies, and the rule's prohibited condition is demonstrated. This diagram-like sequence is a contract example, not recorded project test evidence.
