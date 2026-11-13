"""Allowlisted static registry and bounded JSON-shape validation for R2 tools."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from app.core.schemas.contracts import ToolManifest
from app.sandbox.resources import LabOperationError, SandboxContext
from app.tools.lab_tools import APPROVED_TOOL_TYPES, LabTool, approved_tool_instances


class DuplicateToolError(ValueError):
    pass


class UnknownToolError(LabOperationError):
    def __init__(self) -> None:
        super().__init__("UNKNOWN_TOOL")


def validate_json_shape(value: Any, schema: dict[str, Any]) -> None:
    """Implement the small JSON Schema subset used by these statically defined manifests."""
    expected = schema.get("type")
    type_ok = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
    }
    if expected not in type_ok or not type_ok[expected](value):
        raise LabOperationError("INVALID_INPUT")
    if expected == "object":
        required = schema.get("required", [])
        props = schema.get("properties", {})
        if any(key not in value for key in required):
            raise LabOperationError("INVALID_INPUT")
        if schema.get("additionalProperties") is False and any(key not in props for key in value):
            raise LabOperationError("INVALID_INPUT")
        for key, item in value.items():
            if key in props:
                validate_json_shape(item, props[key])
    elif expected == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            raise LabOperationError("INVALID_INPUT")
        if "items" in schema:
            for item in value:
                validate_json_shape(item, schema["items"])
    elif expected == "string":
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            raise LabOperationError("INVALID_INPUT")
    elif expected == "integer":
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise LabOperationError("INVALID_INPUT")
    if "enum" in schema and value not in schema["enum"]:
        raise LabOperationError("INVALID_INPUT")


def validate_schema_definition(schema: Any) -> None:
    """Reject malformed or unsupported schema definitions at tool-registration time."""
    if not isinstance(schema, dict) or schema.get("type") not in {
            "object", "array", "string", "integer", "boolean"}:
        raise ValueError("Manifest schema must use a supported JSON type")
    kind = schema["type"]
    supported = {
        "object": {"type", "properties", "required", "additionalProperties", "enum"},
        "array": {"type", "items", "minItems", "maxItems", "enum"},
        "string": {"type", "minLength", "maxLength", "enum"},
        "integer": {"type", "minimum", "maximum", "enum"},
        "boolean": {"type", "enum"},
    }
    if set(schema) - supported[kind]:
        raise ValueError("Manifest schema contains unsupported keywords")
    if kind == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if (not isinstance(properties, dict) or not isinstance(required, list)
                or any(not isinstance(name, str) for name in required)
                or not set(required).issubset(properties)):
            raise ValueError("Invalid object schema properties or required fields")
        additional = schema.get("additionalProperties")
        if additional is not None and not isinstance(additional, bool):
            raise ValueError("additionalProperties must be boolean when supplied")
        for child in properties.values():
            validate_schema_definition(child)
    elif kind == "array":
        if not isinstance(schema.get("items"), dict):
            raise ValueError("Array schema requires an item schema")
        for bound in ("minItems", "maxItems"):
            if bound in schema and (not isinstance(schema[bound], int) or schema[bound] < 0):
                raise ValueError("Array bounds must be non-negative integers")
        if schema.get("minItems", 0) > schema.get("maxItems", float("inf")):
            raise ValueError("Array schema minimum exceeds maximum")
        validate_schema_definition(schema["items"])
    elif kind == "string":
        for bound in ("minLength", "maxLength"):
            if bound in schema and (not isinstance(schema[bound], int) or schema[bound] < 0):
                raise ValueError("String bounds must be non-negative integers")
        if schema.get("minLength", 0) > schema.get("maxLength", float("inf")):
            raise ValueError("String schema minimum exceeds maximum")
    elif kind == "integer":
        for bound in ("minimum", "maximum"):
            if bound in schema and (not isinstance(schema[bound], int) or isinstance(schema[bound], bool)):
                raise ValueError("Integer bounds must be integers")
        if schema.get("minimum", float("-inf")) > schema.get("maximum", float("inf")):
            raise ValueError("Integer schema minimum exceeds maximum")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise ValueError("Schema enum must be a non-empty list")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolManifest, LabTool, str]] = {}

    def register(self, tool: LabTool) -> None:
        manifest = ToolManifest.model_validate(tool.manifest.model_dump())
        validate_schema_definition(manifest.input_schema)
        validate_schema_definition(manifest.output_schema)
        approved_type = APPROVED_TOOL_TYPES.get(manifest.tool_id)
        if approved_type is None or type(tool) is not approved_type:
            raise ValueError("Only statically approved tool implementations may be registered")
        if manifest.tool_id in self._tools:
            raise DuplicateToolError("Tool identifier is already registered")
        self._tools[manifest.tool_id] = (manifest, tool,
                                         f"{type(tool).__module__}:{type(tool).__qualname__}")

    def get_manifest(self, tool_id: str) -> ToolManifest:
        try:
            return self._tools[tool_id][0].model_copy(deep=True)
        except KeyError as exc:
            raise UnknownToolError() from exc

    def get_implementation_reference(self, tool_id: str) -> str:
        try:
            return self._tools[tool_id][2]
        except KeyError as exc:
            raise UnknownToolError() from exc

    def list_manifests(self) -> list[ToolManifest]:
        return [self._tools[key][0].model_copy(deep=True) for key in sorted(self._tools)]

    def invoke(self, tool_id: str, payload: dict[str, Any], context: SandboxContext) -> dict[str, Any]:
        try:
            manifest, tool, _ = self._tools[tool_id]
        except KeyError as exc:
            raise UnknownToolError() from exc
        if manifest.status != "ACTIVE":
            raise LabOperationError("TOOL_INACTIVE")
        validate_json_shape(payload, manifest.input_schema)
        result = tool.execute(deepcopy(payload), context)
        validate_json_shape(result, manifest.output_schema)
        return result


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in approved_tool_instances():
        registry.register(tool)
    return registry
