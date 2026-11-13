# Implementation Plan

Phases are gated. Progress to any subsequent phase requires explicit Project Director approval.

| Phase | Scope | Acceptance (summary) | Status |
|---|---|---|---|
| R0 | Workspace audit and portable foundation | Real files, tests, Git/export, no secrets, tablet pending | Accepted administratively per manager directive |
| R1 | Architecture and data contracts | Precise concepts, provenance/coverage, deterministic policy semantics, schemas/tests, recoverability | Accepted by Project Director |
| R2 | Controlled synthetic tool lab | Six statically registered tools; local instrumented operations; evidence, coverage, lineage and simulated sinks | Implemented; 39-test full suite passed; awaiting Project Director review |
| R3 | Declared-vs-observed analysis | Known mismatches and safe cases tested | **Not authorized; not started** |
| R4 | Capability graph and deterministic policies | Evidence-backed composed paths and benign handling | Not authorized; not started |
| R5 | RAG and knowledge base | Genuine retrieval, source attribution, tests | Not authorized; not started |
| R6 | LangGraph workflow | Meaningful nodes, tools, RAG, persisted state | Not authorized; not started |
| R7 | Remediation verification | Dangerous path blocked; legitimate case preserved | Not authorized; not started |
| R8 | Database/backend integration | Actual CRUD and validated API | Not authorized; not started |
| R9 | Security/external services | Auth, storage, limits, audit, proxy tested or pending | Not authorized; not started |
| R10 | Functional dashboard | 11 connected pages and responsive behavior | Not authorized; not started |
| R11 | Benchmark/final integration | Reproducible metrics and documented evidence | Not authorized; not started |
| T1-T3 | Tablet audit, transfer, runtime | Actual target-device checks | Forbidden until tablet available |

## R2 stop point

R2 was explicitly authorized and implemented as a process-local synthetic laboratory. The full current unit suite passed. Submit `MANAGER_HANDOFF_R2.txt` for director review and stop. R3 is not authorized; do not implement R3 or later phases unless the Project Director explicitly approves them.
