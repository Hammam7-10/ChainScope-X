"""Typed request and plan contracts for the single R4 workflow."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas.contracts import Classification


ScenarioId = Literal["A", "B", "C", "D"]


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=3, max_length=1_200)
    scenario_id: ScenarioId
    clearance: Classification = Classification.INTERNAL
    mode: Literal["mock", "live"] = "mock"


class ProposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_id: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any]


class ProposedPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[ProposedAction] = Field(min_length=1, max_length=4)


SCENARIO_TOOL_ALLOWLIST: dict[str, frozenset[str]] = {
    "A": frozenset({"data-transformer", "workspace-storage"}),
    "B": frozenset({"file-creator", "workspace-storage"}),
    "C": frozenset({"data-transformer", "workspace-storage", "file-sharing"}),
    "D": frozenset({"document-reader"}),
}

SCENARIO_REQUIRED_DOCUMENT: dict[str, str] = {
    "A": "DOC-INTERNAL-SAFE-001",
    "B": "DOC-WORKSPACE-ANOMALY-001",
    "C": "DOC-CONFIDENTIAL-EXTERNAL-001",
    "D": "DOC-MONITORING-COMPLETENESS-001",
}
