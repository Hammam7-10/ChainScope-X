"""Run one bounded ChainScope X synthetic workflow and emit structured JSON."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from app.agent.contracts import AgentRequest
from app.agent.workflow import ChainScopeWorkflow
from app.core.schemas.contracts import Classification


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one bounded synthetic ChainScope X test")
    parser.add_argument("--scenario", choices=("A", "B", "C", "D"), required=True)
    parser.add_argument("--query", required=True, help="User testing request (max 1,200 characters)")
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--clearance", choices=tuple(item.value for item in Classification),
                        default=Classification.INTERNAL.value)
    args = parser.parse_args(argv)
    try:
        state = ChainScopeWorkflow().invoke(AgentRequest(
            query=args.query,
            scenario_id=args.scenario,
            mode=args.mode,
            clearance=Classification(args.clearance),
        ))
    except Exception:
        print(json.dumps({"workflow_status": "FAILED", "error_codes": ["workflow_initialization_failed"]},
                         ensure_ascii=False))
        return 2
    if "final_report" in state:
        output = state["final_report"]
        exit_code = 0
    else:
        output = {
            "workflow_status": state.get("workflow_status", "FAILED"),
            "scenario_id": args.scenario,
            "planner_mode": state.get("planner_mode", args.mode),
            "model_id": state.get("model_id"),
            "live_model_verified": bool(state.get("live_model_verified", False)),
            "tool_execution_started": "execution_report" in state,
            "error_codes": state.get("error_codes", []),
        }
        exit_code = 2
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
