"""Export stable JSON Schema snapshots for the R1 Pydantic contracts."""
import json
from pathlib import Path

from app.core.schemas.contracts import (
    CapabilityPath, CoverageRecord, Finding, GraphEdge, GraphNode, ObservedEffect,
    PolicyRule, RemediationCandidate, ToolManifest, VerificationRun,
)

MODELS = [ToolManifest, CoverageRecord, ObservedEffect, GraphNode, GraphEdge,
          CapabilityPath, PolicyRule, Finding, RemediationCandidate, VerificationRun]
OUTPUT = Path(__file__).with_name("json")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        path = OUTPUT / f"{model.__name__}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Exported {len(MODELS)} schemas to {OUTPUT}")


if __name__ == "__main__":
    main()
