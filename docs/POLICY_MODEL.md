# Deterministic Policy Model (R1)

## Rule record
A machine rule has `rule_id`, immutable `version`, `kind`, explicit `scope`, structured `conditions`, `outcome` (initially DENY or REQUIRE_APPROVAL), effective dates, `active` status, and required evidence kinds. A rule evaluation records rule version, event/path IDs, matched conditions, decision, and coverage limitations. No free-form natural-language rule is directly executable.

## Initial rule kinds
- `CONFIDENTIAL_TO_UNAUTHORIZED_DESTINATION`: prohibit confidential/restricted data from reaching a destination unless the destination is explicitly authorized for that classification and operation.
- `RESTRICT_ASSET_ACCESS`: prohibit reads/searches against assets outside the tool's approved resource scope.
- `RESTRICT_WRITE_DESTINATION`: prohibit writes to unapproved destinations/folders.
- `APPROVAL_REQUIRED`: require an approval event linked to the same operation, actor/context, and policy scope before execution is considered authorized.
- `PROHIBIT_DESTINATION`: deny any effect targeting an explicitly forbidden destination.

## Deterministic decision requirements
For a confirmed violation, require an active effective rule, demonstrated scope/conditions, structured observed events, and an event-backed graph path where composition is claimed. If a needed fact is missing, return insufficient evidence/inconclusive rather than guessing. A positive observed prohibited event may establish a violation even with incomplete broader monitoring; a negative assessment requires COMPLETE coverage within declared tested scope.

## Severity (bounded criteria)
CRITICAL: observed restricted/confidential data transmitted to an explicitly prohibited or unauthorized external destination with a complete event-backed path. HIGH: other confirmed high-impact unauthorized sensitive access/write/transmission. MEDIUM: confirmed lower-sensitivity policy breach or material declared/observed discrepancy with impact. LOW: limited-scope mismatch or weakly impactful policy failure. INFORMATIONAL: benign mismatch, coverage limitation, or trace context without proven breach. Severity is an ordinal human-readable category, not a numeric confidence score; implementation must state the evidence-based rationale and may use higher severity only with documented rubric.

## Distinctions
- Policy document: human-readable, versioned guidance text.
- Policy rule: structured machine-readable condition/outcome.
- RAG retrieval: retrieves source passages for context/explanation, never authorizes or proves a violation.
- Policy evaluation: deterministic comparison of recorded facts to the active structured rule.
- Finding: reports outcome plus evidence, uncertainty, coverage, and provenance.

LLM text cannot add events, invent paths, determine the authoritative verdict, or silently downgrade classification.
