ChainScope X

AI-Powered Agent Security, Policy Compliance & Evidence Analysis

ChainScope X is an AI-powered security analysis platform designed to inspect agentic systems, evaluate their interactions with tools and resources, and identify behavioral deviations from defined policies and declared capabilities.

Combining LangGraph agent orchestration, Retrieval-Augmented Generation (RAG), execution analysis, and evidence-based reporting, ChainScope X transforms complex agent interactions into structured, traceable security findings.

Overview

As AI agents gain the ability to interact with tools, services, and organizational resources, monitoring their behavior and ensuring policy compliance becomes essential.

ChainScope X addresses this challenge through an intelligent analysis workflow that retrieves relevant policies, inspects registered resources and capabilities, plans and validates operations, analyzes execution results, and generates structured findings.

The platform provides a centralized dashboard for reviewing analysis runs, exploring evidence, investigating findings, and managing policy documents.

Key Features

- AI Agent Orchestration: Multi-stage analysis workflows powered by LangGraph.
- Policy-Aware RAG: Semantic policy retrieval using vector embeddings and ChromaDB.
- Resource Inspection: Analysis of registered resources and declared capabilities.
- Execution Planning: Structured planning and validation before tool execution.
- Evidence-Based Analysis: Comparison of observed effects with expected behavior and applicable policies.
- Security Findings: Structured assessments with finding types, severity levels, classifications, and evidence references.
- Persistent Analysis History: Records of analysis runs, events, timelines, and findings.
- Policy Management: Policy indexing, semantic search, inspection, and deactivation.
- Interactive Dashboard: Centralized access to analysis results, evidence, and policies.
- Application Security: Google authentication, role-based access control, and API rate limiting.

How It Works

The LangGraph agent coordinates the following workflow:

1. Request Validation – Validates the incoming analysis request.
2. Policy Retrieval – Retrieves relevant policies through RAG.
3. Registry Inspection – Examines registered resources and capabilities.
4. Test Planning – Develops an analysis plan.
5. Plan Validation – Validates the proposed operations.
6. Tool Execution – Executes the selected analysis operations.
7. Execution Analysis – Evaluates observed effects against expected behavior and policies.
8. Evidence Reporting – Generates structured findings and persists the results.

This makes ChainScope X an analysis agent rather than a conventional conversational chatbot: it coordinates workflows, interacts with tools, evaluates results, and produces traceable outputs.

System Architecture

flowchart TD
    U[User] --> UI[Web Dashboard]
    UI --> API[FastAPI Backend]

    API --> AUTH[Authentication and RBAC]
    API --> AGENT[LangGraph Agent]

    AGENT --> RAG[RAG Policy Retrieval]
    RAG --> CHROMA[(ChromaDB)]

    AGENT --> REG[Resource Registry]
    AGENT --> PLAN[Planning and Validation]
    PLAN --> TOOLS[Analysis Tools]
    TOOLS --> EVAL[Evidence Analysis]

    EVAL --> FIND[Security Findings]
    FIND --> PG[(PostgreSQL)]
    FIND --> MONGO[(MongoDB)]

    PG --> API
    MONGO --> API
    API --> UI

Findings and Assessment

Each finding provides a structured representation of an identified condition, including:

Attribute| Description
Finding Type| Category of the detected condition.
Assessment| Analytical conclusion.
Severity| Potential impact or risk level.
Classification| Sensitivity level of related information.
Evidence References| Supporting execution evidence.
Analysis Run| Associated analysis record.

The assessment model distinguishes confirmed policy violations, behavioral mismatches, potential risks, and inconclusive outcomes.

Web Dashboard

The application provides dedicated areas for:

- Dashboard and system overview.
- Findings Explorer and finding details.
- Analysis runs and analysis details.
- Evidence exploration and execution timelines.
- New analysis requests.
- Policy management and policy details.
- Account and access information.

Security

ChainScope X integrates multiple application security controls:

- Google OAuth 2.0 for authentication.
- Role-Based Access Control (RBAC) for authorization.
- API Rate Limiting for request protection.
- CSRF Protection for protected operations.
- Role Separation across administrative, analytical, and read-only access.

Role| Access
Admin| Administrative and authorized operational access.
Analyst| Authorized analysis operations.
Viewer| Read-only access to permitted information.

Technology Stack

Category| Technologies
Language| Python
Backend| FastAPI
Agent Orchestration| LangGraph
AI Knowledge Retrieval| RAG
Vector Database| ChromaDB
Relational Database| PostgreSQL
NoSQL Database| MongoDB
Authentication| Google OAuth 2.0
Security| RBAC, Rate Limiting, CSRF
Database Migrations| Alembic
Interface| Web-Based Dashboard

Project Structure

ChainScope-X/
├── app/
│   ├── agent/
│   ├── api/
│   ├── security/
│   └── main.py
├── data/
│   └── policies/
├── docs/
├── alembic/
├── tests/
├── requirements.txt
└── .env.example

Installation

1. Clone the Repository

git clone https://github.com/Hammam7-10/ChainScope-X.git
cd ChainScope-X

2. Create and Activate a Virtual Environment

python -m venv .venv
source .venv/bin/activate

3. Install Dependencies

pip install -r requirements.txt

4. Configure Environment Variables

cp .env.example .env

Configure the required database connections, authentication settings, and AI provider credentials.

5. Apply Database Migrations

alembic upgrade head

6. Run the Application

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Access the Application

Resource| URL
Web Dashboard| "http://127.0.0.1:8000/app"
Health Check| "http://127.0.0.1:8000/health"
OpenAPI Schema| "http://127.0.0.1:8000/openapi.json"

---

Vision

ChainScope X aims to make AI agent behavior more transparent, traceable, and accountable by connecting policy awareness, resource inspection, controlled execution, and evidence-based security analysis in one integrated platform.

ChainScope X — Bringing visibility, policy awareness, and accountability to agentic systems.