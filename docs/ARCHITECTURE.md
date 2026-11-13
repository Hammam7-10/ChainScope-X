# Architecture (R1 target design)

## Decisions and boundaries
A lightweight server-rendered FastAPI web application remains the approved direction: Jinja2, HTMX and vanilla JS with local assets; no frontend framework change. Application logic is layered (API/templates → services → deterministic domain engines → repositories), with PostgreSQL relational persistence, ChromaDB only for vector retrieval, a controlled synthetic tool lab, and LangGraph as future orchestration. Hosted Groq is optional/configurable; deterministic mock mode remains. R1 implements only domain validation contracts, not these integrated services.

Monitoring claims are limited to events emitted by the tested controlled instrumentation layer. Coverage is explicit per run. There is no claim of OS-wide or complete external side-effect observation. Policy verdicts are deterministic and event-backed; RAG/LLM may retrieve or explain but cannot create evidence or decide authoritative violations.

## System architecture
```mermaid
flowchart LR
  Browser[Browser: Jinja2 + HTMX + local JS/CSS] --> API[FastAPI routes]
  API --> SVC[Application services]
  SVC --> WF[LangGraph workflow]
  WF --> LAB[Controlled synthetic tool lab]
  LAB --> REC[Effect recorder + coverage]
  REC --> ENG[Normalization + graph + deterministic policy]
  ENG --> PG[(PostgreSQL: records/evidence refs)]
  SVC --> RAG[Retrieval service]
  RAG --> CH[(Chroma vector index)]
  RAG -. contextual text only .-> WF
  WF -. optional explanation/planning .-> LLM[Configurable Groq or mock]
  API --> AUTH[Supabase Auth/JWT in later integration]
  SVC --> STORE[Private object storage in later integration]
```

## Core entity relationships
```mermaid
erDiagram
  TOOL ||--o{ TOOL_VERSION : versions
  TOOL_VERSION ||--o{ DECLARED_CAPABILITY : declares
  TOOL_VERSION ||--o{ DECLARED_EFFECT : declares
  TEST_CAMPAIGN ||--o{ EXECUTION_RUN : contains
  TEST_SCENARIO ||--o{ EXECUTION_RUN : exercises
  EXECUTION_RUN ||--o{ TOOL_INVOCATION : includes
  TOOL_VERSION ||--o{ TOOL_INVOCATION : invoked_as
  TOOL_INVOCATION ||--o{ OBSERVED_EFFECT : emits
  EXECUTION_RUN ||--|| INSTRUMENTATION_COVERAGE : reports
  EXECUTION_RUN ||--o{ CAPABILITY_EDGE : derives
  CAPABILITY_EDGE }o--o{ OBSERVED_EFFECT : supported_by
  POLICY ||--o{ POLICY_VERSION : versions
  EXECUTION_RUN ||--o{ FINDING : yields
  POLICY_VERSION o|--o{ FINDING : supports
  FINDING ||--o{ REMEDIATION_CANDIDATE : addressed_by
  REMEDIATION_CANDIDATE ||--o{ VERIFICATION_RUN : tested_by
```

## Effect capture and analysis flow
```mermaid
sequenceDiagram
  participant O as Orchestrator
  participant T as Registered synthetic tool
  participant I as Instrumentation boundary
  participant C as Coverage record
  participant G as Graph/policy evaluator
  participant P as Persistence
  O->>T: invoke(tool_id, invocation_id, execution_id)
  T->>I: report controlled operation + evidence
  I->>I: validate IDs, sequence, scope, classification
  I->>C: record monitored scope and gaps/status
  I->>G: immutable event references
  G->>G: compare declaration; construct only event-backed edges
  G->>G: evaluate active deterministic rules
  G->>P: findings + evidence links + coverage + uncertainty
```

## Composed path
```mermaid
flowchart LR
  A[Confidential asset] -->|READS: event e1| T1[Document Reader]
  T1 -->|TRANSFORMS: event e2| T2[Report Generator]
  T2 -->|TRANSMITS: event e3| D[Unauthorized destination]
  P[Active policy + version] -. evaluated against linked path .-> F[Finding only with evidence]
  C[Coverage + scope + gaps] --> F
```

## Remediation / verification lifecycle
```mermaid
stateDiagram-v2
  [*] --> Proposed
  Proposed --> ApprovedForIsolatedTest: authorized review
  ApprovedForIsolatedTest --> Tested: dangerous + benign + alternative scenarios run
  Tested --> Verified: criteria pass and evidence retained
  Tested --> Failed: path remains or benign flow breaks
  Tested --> Inconclusive: coverage/evidence insufficient
  Verified --> Proposed: policy/tool version changes
```

## Data and trust zones
Synthetic test fixtures and local simulated sinks are isolated from real external destinations. The recorder produces structured facts and evidence references; the graph and policy engine operate deterministically. Retrieved documents and LLM output are untrusted context. No secret is placed in browser code. Production identity, database, and object storage integrations are fail-closed and later-phase work.
