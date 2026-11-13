"""Deterministic allowlist validation and bounded output-reference resolution."""
from __future__ import annotations

import re
from typing import Any

from app.agent.contracts import ProposedPlan, SCENARIO_TOOL_ALLOWLIST
from app.core.schemas.contracts import ToolManifest
from app.tools.registry import ToolRegistry, validate_json_shape


_REFERENCE = re.compile(r"^\$ref:(\d+)\.output\.([A-Za-z0-9_]+)$")
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_ACTIONS = 4


class PlanRejection(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _is_reference(value: Any) -> bool:
    return isinstance(value, str) and _REFERENCE.fullmatch(value) is not None


def _placeholder(schema: dict[str, Any]) -> Any:
    kind = schema.get("type")
    if kind == "string":
        return "synthetic-reference"
    if kind == "integer":
        return int(schema.get("minimum", 1))
    if kind == "boolean":
        return False
    if kind == "array":
        item = _placeholder(schema.get("items", {"type": "string"}))
        return [item] * int(schema.get("minItems", 0))
    if kind == "object":
        properties = schema.get("properties", {})
        return {name: _placeholder(properties[name]) for name in schema.get("required", [])}
    raise PlanRejection("unsupported_reference_output_type")


def _resolve_references(value: Any, *, action_index: int, actions: list[dict[str, Any]],
                        manifests: dict[str, ToolManifest], outputs: list[dict[str, Any]] | None) -> Any:
    if isinstance(value, str) and value.startswith("$ref:"):
        match = _REFERENCE.fullmatch(value)
        if match is None:
            raise PlanRejection("malformed_output_reference")
        step_index = int(match.group(1))
        field = match.group(2)
        if step_index >= action_index:
            raise PlanRejection("output_reference_must_target_an_earlier_action")
        source_tool = actions[step_index]["tool_id"]
        source_manifest = manifests.get(source_tool)
        if source_manifest is None:
            raise PlanRejection("output_reference_source_tool_not_approved")
        output_properties = source_manifest.output_schema.get("properties", {})
        field_schema = output_properties.get(field)
        if not isinstance(field_schema, dict):
            raise PlanRejection("output_reference_field_not_declared")
        if outputs is None:
            return _placeholder(field_schema)
        if step_index >= len(outputs) or not isinstance(outputs[step_index].get("output"), dict):
            raise PlanRejection("output_reference_source_not_available")
        actual_output = outputs[step_index]["output"]
        if field not in actual_output:
            raise PlanRejection("output_reference_field_missing")
        return actual_output[field]
    if isinstance(value, str) and "$ref" in value:
        raise PlanRejection("malformed_output_reference")
    if isinstance(value, list):
        return [_resolve_references(item, action_index=action_index, actions=actions,
                                    manifests=manifests, outputs=outputs) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_references(item, action_index=action_index, actions=actions,
                                         manifests=manifests, outputs=outputs)
                for key, item in value.items()}
    return value


def _check_input_policy(value: Any, *, manifest: ToolManifest, key: str = "",
                        allow_resolved_file: bool = False) -> None:
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _check_input_policy(child_value, manifest=manifest, key=child_key,
                                 allow_resolved_file=allow_resolved_file)
        return
    if isinstance(value, list):
        for child in value:
            _check_input_policy(child, manifest=manifest, key=key,
                                 allow_resolved_file=allow_resolved_file)
        return
    if not isinstance(value, str):
        return
    if "://" in value or value.startswith(("/", "\\")) or "../" in value:
        raise PlanRejection("real_url_or_filesystem_target_forbidden")
    if key in {"asset_id", "asset_ids", "dataset_id"}:
        if value not in manifest.allowed_resources:
            raise PlanRejection("resource_not_in_manifest_allowlist")
    elif key == "destination_id":
        if value not in manifest.allowed_destinations or not value.startswith("destination:"):
            raise PlanRejection("destination_not_in_simulated_allowlist")
    elif key == "file_id":
        if not _is_reference(value) and not (
                allow_resolved_file and value.startswith(("file:", "stored:"))):
            raise PlanRejection("file_reference_must_come_from_an_approved_prior_tool")
    elif key == "filename" and not _SAFE_FILENAME.fullmatch(value):
        raise PlanRejection("unsafe_filename")


def validate_plan(raw_plan: Any, *, scenario_id: str, registry: ToolRegistry) -> ProposedPlan:
    try:
        plan = raw_plan if isinstance(raw_plan, ProposedPlan) else ProposedPlan.model_validate(raw_plan)
    except Exception as exc:
        raise PlanRejection("invalid_plan_shape") from exc
    if len(plan.actions) > MAX_ACTIONS:
        raise PlanRejection("plan_exceeds_action_limit")
    allowed_for_scenario = SCENARIO_TOOL_ALLOWLIST.get(scenario_id)
    if allowed_for_scenario is None:
        raise PlanRejection("unsupported_test_scenario")
    manifests = {manifest.tool_id: manifest for manifest in registry.list_manifests()}
    if len(manifests) != 6:
        raise PlanRejection("approved_registry_must_contain_exactly_six_tools")
    actions = [action.model_dump(mode="python") for action in plan.actions]
    for index, action in enumerate(actions):
        tool_id = action["tool_id"]
        manifest = manifests.get(tool_id)
        if manifest is None or manifest.status != "ACTIVE":
            raise PlanRejection("tool_not_in_approved_registry")
        if tool_id not in allowed_for_scenario:
            raise PlanRejection("tool_not_allowed_for_selected_scenario")
        arguments = action["arguments"]
        if not isinstance(arguments, dict):
            raise PlanRejection("tool_arguments_must_be_object")
        _check_input_policy(arguments, manifest=manifest)
        shape_checked_arguments = _resolve_references(
            arguments, action_index=index, actions=actions, manifests=manifests, outputs=None)
        try:
            validate_json_shape(shape_checked_arguments, manifest.input_schema)
        except Exception as exc:
            raise PlanRejection("arguments_do_not_match_tool_manifest") from exc
    return plan


def resolve_action_arguments(plan: ProposedPlan, action_index: int, outputs: list[dict[str, Any]],
                             registry: ToolRegistry) -> dict[str, Any]:
    actions = [action.model_dump(mode="python") for action in plan.actions]
    manifests = {manifest.tool_id: manifest for manifest in registry.list_manifests()}
    action = actions[action_index]
    manifest = manifests[action["tool_id"]]
    resolved = _resolve_references(action["arguments"], action_index=action_index,
                                   actions=actions, manifests=manifests, outputs=outputs)
    if not isinstance(resolved, dict):
        raise PlanRejection("resolved_arguments_must_be_object")
    _check_input_policy(resolved, manifest=manifest, allow_resolved_file=True)
    try:
        validate_json_shape(resolved, manifest.input_schema)
    except Exception as exc:
        raise PlanRejection("resolved_arguments_do_not_match_tool_manifest") from exc
    return resolved
