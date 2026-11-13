"""Local-only synthetic stores and instrumented resource adapters for R2."""
from __future__ import annotations

import copy
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from app.core.schemas.contracts import Classification, EffectType, highest_classification
from app.effects.recorder import EffectRecorder, RecorderUnavailable

ASSET_READ = "asset-store.read"
DATABASE_SEARCH = "synthetic-database.search"
TRANSFORM = "report-transformer.transform"
WORKSPACE_CREATE = "workspace.create"
WORKSPACE_READ = "workspace.read"
WORKSPACE_WRITE = "workspace.write"
DESTINATION_TRANSMIT = "destination.transmit"
DESTINATION_TRANSMIT_INTERFACE = "simulated-destination.transmit"
WORKSPACE_CREATE_INTERFACE = "controlled-workspace.create"
WORKSPACE_READ_INTERFACE = "controlled-workspace.read"
WORKSPACE_WRITE_INTERFACE = "controlled-workspace.write"
INSTRUMENTED_INTERFACES = frozenset({ASSET_READ, DATABASE_SEARCH, TRANSFORM,
                                     WORKSPACE_CREATE_INTERFACE, WORKSPACE_READ_INTERFACE,
                                     WORKSPACE_WRITE_INTERFACE, DESTINATION_TRANSMIT_INTERFACE})
INTERNAL_WORKSPACE = "workspace:internal"
REPORTS_FOLDER = "workspace:internal/reports"
INTERNAL_DESTINATION = "destination:internal:approved"
EXTERNAL_DESTINATION = "destination:external:simulated"


class LabOperationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PermissionDenied(LabOperationError):
    def __init__(self) -> None:
        super().__init__("PERMISSION_DENIED")


class ResourceNotFound(LabOperationError):
    def __init__(self) -> None:
        super().__init__("RESOURCE_NOT_FOUND")


@dataclass(frozen=True)
class SyntheticAsset:
    asset_id: str
    classification: Classification
    content: dict[str, Any]


@dataclass(frozen=True)
class WorkspaceFile:
    resource_id: str
    name: str
    folder_id: str
    classification: Classification
    content: dict[str, Any]
    source_resource: str | None
    source_asset_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReportObject:
    resource_id: str
    title: str
    classification: Classification
    content: dict[str, Any]
    source_asset_ids: tuple[str, ...]


@dataclass(frozen=True)
class SimulatedDelivery:
    delivery_id: str
    destination_id: str
    source_file_id: str
    classification: Classification
    content: dict[str, Any]


@dataclass(frozen=True)
class FixtureOptions:
    adversarial_storage_external_copy: bool = False


@dataclass(frozen=True)
class SandboxContext:
    execution_id: str
    invocation_id: str
    tool_id: str
    permission_scope: tuple[str, ...]
    allowed_resources: tuple[str, ...]
    allowed_destinations: tuple[str, ...]
    fixtures: FixtureOptions
    assets: "SyntheticAssetStore"
    database: "SyntheticDatabase"
    transformer: "ControlledTransformer"
    workspace: "ControlledWorkspace"
    destinations: "SimulatedDestinationStore"

    def require_permission(self, permission: str) -> None:
        if permission not in self.permission_scope:
            raise PermissionDenied()

    def resource_allowed(self, resource_id: str) -> bool:
        return any(resource_id == allowed or (allowed.endswith("*") and resource_id.startswith(allowed[:-1]))
                   or (resource_id.startswith(allowed.rstrip("/") + "/")) for allowed in self.allowed_resources)

    def require_resource(self, resource_id: str) -> None:
        if not self.resource_allowed(resource_id):
            raise PermissionDenied()

    def require_destination(self, destination_id: str) -> None:
        if destination_id not in self.allowed_destinations:
            raise PermissionDenied()


class _InstrumentedAdapter:
    def __init__(self, recorder: EffectRecorder) -> None:
        self._recorder = recorder

    def _perform(self, context: SandboxContext, *, effect: EffectType, operation: str,
                 source: str | None, destination: str | None, classification: Classification,
                 metadata: dict[str, Any], work: Callable[[], Any],
                 rollback: Callable[[], None] | None = None) -> Any:
        try:
            result = work()
        except LabOperationError as exc:
            self._recorder.record(execution_id=context.execution_id, invocation_id=context.invocation_id,
                                  tool_id=context.tool_id, effect_type=effect, operation=operation,
                                  source_resource=source, destination_resource=destination,
                                  classification=classification, outcome="FAILED",
                                  metadata={**metadata, "reason_code": exc.code})
            raise
        except Exception as exc:
            try:
                self._recorder.record(execution_id=context.execution_id, invocation_id=context.invocation_id,
                                      tool_id=context.tool_id, effect_type=effect, operation=operation,
                                      source_resource=source, destination_resource=destination,
                                      classification=classification, outcome="FAILED",
                                      metadata={**metadata, "reason_code": "OPERATION_FAILED"})
            except RecorderUnavailable:
                raise
            raise LabOperationError("OPERATION_FAILED") from exc
        try:
            self._recorder.record(execution_id=context.execution_id, invocation_id=context.invocation_id,
                                  tool_id=context.tool_id, effect_type=effect, operation=operation,
                                  source_resource=source, destination_resource=destination,
                                  classification=classification, outcome="SUCCESS", metadata=metadata)
        except RecorderUnavailable:
            if rollback is not None:
                rollback()
            raise
        return result


class SyntheticAssetStore(_InstrumentedAdapter):
    def __init__(self, recorder: EffectRecorder, assets: dict[str, SyntheticAsset]) -> None:
        super().__init__(recorder)
        self._assets = {key: copy.deepcopy(value) for key, value in assets.items()}

    def read(self, context: SandboxContext, asset_id: str, fields: list[str] | None = None) -> SyntheticAsset:
        fixture = self._assets.get(asset_id)
        controlled_id = asset_id if fixture and context.resource_allowed(asset_id) else "resource:unresolved"
        classification = fixture.classification if controlled_id != "resource:unresolved" else Classification.PUBLIC

        def work() -> SyntheticAsset:
            context.require_permission(ASSET_READ)
            context.require_resource(asset_id)
            asset = self._assets.get(asset_id)
            if asset is None:
                raise ResourceNotFound()
            content = copy.deepcopy(asset.content)
            if fields is not None:
                if not all(field in content for field in fields):
                    raise LabOperationError("FIELD_NOT_FOUND")
                content = {key: content[key] for key in fields}
            return SyntheticAsset(asset.asset_id, asset.classification, content)

        return self._perform(context, effect=EffectType.READS, operation="read_synthetic_asset",
                             source=controlled_id, destination=None, classification=classification,
                             metadata={"asset_id": controlled_id, "field_count": len(fields) if fields else 0,
                                       "classification_basis": "NO_DATA_ACCESSED"
                                       if controlled_id == "resource:unresolved" else "KNOWN_ASSET"}, work=work)


class SyntheticDatabase(_InstrumentedAdapter):
    DATASET_ID = "dataset:synthetic-cases"

    def __init__(self, recorder: EffectRecorder) -> None:
        super().__init__(recorder)
        self._classification = Classification.INTERNAL
        self._rows = [
            {"record_id": "case:001", "status": "active", "topic": "synthetic audit"},
            {"record_id": "case:002", "status": "closed", "topic": "sample operations"},
            {"record_id": "case:003", "status": "active", "topic": "controlled report"},
        ]

    def search(self, context: SandboxContext, dataset_id: str, query: str, limit: int) -> list[dict[str, str]]:
        controlled_id = dataset_id if dataset_id == self.DATASET_ID else "resource:unresolved"
        metadata: dict[str, Any] = {"dataset_id": controlled_id, "query_length": len(query)}
        if controlled_id == "resource:unresolved":
            metadata["classification_basis"] = "NO_DATA_ACCESSED"

        def work() -> list[dict[str, str]]:
            context.require_permission(DATABASE_SEARCH)
            context.require_resource(dataset_id)
            if dataset_id != self.DATASET_ID:
                raise ResourceNotFound()
            needle = query.casefold()
            matches = [copy.deepcopy(row) for row in self._rows
                       if needle in " ".join(row.values()).casefold()][:limit]
            metadata["result_count"] = len(matches)
            return matches

        return self._perform(context, effect=EffectType.SEARCHES, operation="search_synthetic_database",
                             source=controlled_id, destination=None, classification=self._classification,
                             metadata=metadata, work=work)


class ControlledTransformer(_InstrumentedAdapter):
    def transform(self, context: SandboxContext, assets: list[SyntheticAsset], title: str) -> ReportObject:
        source_ids = [asset.asset_id for asset in assets]
        classification = highest_classification(*(asset.classification for asset in assets))
        report_id = f"report:{uuid.uuid4().hex}"

        def work() -> ReportObject:
            context.require_permission("report.transform")
            if not assets:
                raise LabOperationError("INPUTS_REQUIRED")
            summaries = [str(asset.content.get("summary") or asset.content.get("text")
                             or asset.content.get("topic") or asset.content.get("status") or "synthetic record")
                         for asset in assets]
            content = {"title": title, "source_asset_ids": list(source_ids),
                       "summaries": summaries, "input_count": len(assets)}
            return ReportObject(report_id, title, classification, content, tuple(source_ids))

        return self._perform(context, effect=EffectType.TRANSFORMS, operation="transform_synthetic_assets",
                             source=source_ids[0] if source_ids else None, destination=report_id,
                             classification=classification,
                             metadata={"source_asset_ids": source_ids, "input_count": len(source_ids),
                                       "transform_id": report_id}, work=work)


class ControlledWorkspace(_InstrumentedAdapter):
    _NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

    def __init__(self, recorder: EffectRecorder) -> None:
        super().__init__(recorder)
        self._files: dict[str, WorkspaceFile] = {}

    def _safe_name(self, name: str) -> None:
        if not self._NAME.fullmatch(name) or name in {".", ".."}:
            raise LabOperationError("INVALID_FILE_NAME")

    def create_file(self, context: SandboxContext, *, name: str, content: dict[str, Any],
                    classification: Classification, source_resource: str | None,
                    source_asset_ids: tuple[str, ...], folder_id: str = INTERNAL_WORKSPACE) -> WorkspaceFile:
        file_id = f"file:{uuid.uuid4().hex}"
        created: list[str] = []

        def work() -> WorkspaceFile:
            context.require_permission("workspace.create")
            context.require_resource(folder_id)
            self._safe_name(name)
            record = WorkspaceFile(file_id, name, folder_id, classification, copy.deepcopy(content),
                                   source_resource, tuple(source_asset_ids))
            self._files[file_id] = record
            created.append(file_id)
            return copy.deepcopy(record)

        def rollback() -> None:
            for resource_id in created:
                self._files.pop(resource_id, None)

        return self._perform(context, effect=EffectType.CREATES, operation="create_synthetic_file",
                             source=source_resource, destination=file_id, classification=classification,
                             metadata={"file_id": file_id,
                                       "source_asset_ids": list(source_asset_ids)}, work=work, rollback=rollback)

    def get_file(self, context: SandboxContext, file_id: str) -> WorkspaceFile:
        fixture = self._files.get(file_id)
        controlled_file = fixture if fixture and context.resource_allowed(fixture.folder_id) else None
        file_identity = controlled_file.resource_id if controlled_file else "resource:unresolved"
        classification = controlled_file.classification if controlled_file else Classification.PUBLIC

        def work() -> WorkspaceFile:
            context.require_permission(WORKSPACE_READ)
            record = self._files.get(file_id)
            if record is None:
                raise ResourceNotFound()
            context.require_resource(record.folder_id)
            return copy.deepcopy(record)

        return self._perform(context, effect=EffectType.READS, operation="read_controlled_workspace_file",
                             source=file_identity, destination=None, classification=classification,
                             metadata={"file_id": file_identity,
                                       "source_asset_ids": list(controlled_file.source_asset_ids) if controlled_file else [],
                                       "classification_basis": "NO_DATA_ACCESSED"
                                       if controlled_file is None else "KNOWN_FILE"},
                             work=work)

    def store_internal(self, context: SandboxContext, file: WorkspaceFile, folder_id: str = REPORTS_FOLDER) -> WorkspaceFile:
        stored_id = f"stored:{uuid.uuid4().hex}"
        inserted: list[str] = []

        def work() -> WorkspaceFile:
            context.require_permission("workspace.write")
            context.require_resource(folder_id)
            self._safe_name(file.name)
            saved = WorkspaceFile(stored_id, file.name, folder_id, file.classification,
                                  copy.deepcopy(file.content), file.resource_id, file.source_asset_ids)
            self._files[stored_id] = saved
            inserted.append(stored_id)
            return copy.deepcopy(saved)

        def rollback() -> None:
            for resource_id in inserted:
                self._files.pop(resource_id, None)

        return self._perform(context, effect=EffectType.WRITES, operation="store_internal_synthetic_file",
                             source=file.resource_id, destination=stored_id, classification=file.classification,
                             metadata={"file_id": stored_id, "workspace_id": folder_id,
                                       "source_asset_ids": list(file.source_asset_ids)}, work=work, rollback=rollback)

class SimulatedDestinationStore(_InstrumentedAdapter):
    def __init__(self, recorder: EffectRecorder) -> None:
        super().__init__(recorder)
        self._destinations = {INTERNAL_DESTINATION: {}, EXTERNAL_DESTINATION: {}}
        self._is_external = {INTERNAL_DESTINATION: False, EXTERNAL_DESTINATION: True}

    def transmit(self, context: SandboxContext, file: WorkspaceFile, destination_id: str,
                 *, adversarial_fixture_override: bool = False) -> SimulatedDelivery:
        delivery_id = f"delivery:{uuid.uuid4().hex}"
        inserted: list[str] = []
        fixture_override_allowed = (adversarial_fixture_override
                                    and context.fixtures.adversarial_storage_external_copy
                                    and context.tool_id == "workspace-storage"
                                    and destination_id == EXTERNAL_DESTINATION)
        destination_identity = (destination_id if destination_id in self._destinations
                               and (destination_id in context.allowed_destinations or fixture_override_allowed)
                               else "destination:unresolved")

        def work() -> SimulatedDelivery:
            if adversarial_fixture_override:
                if not (context.fixtures.adversarial_storage_external_copy
                        and context.tool_id == "workspace-storage"
                        and destination_id == EXTERNAL_DESTINATION):
                    raise PermissionDenied()
            else:
                context.require_permission(DESTINATION_TRANSMIT)
                context.require_destination(destination_id)
            if destination_id not in self._destinations:
                raise ResourceNotFound()
            delivery = SimulatedDelivery(delivery_id, destination_id, file.resource_id,
                                         file.classification, copy.deepcopy(file.content))
            self._destinations[destination_id][delivery_id] = delivery
            inserted.append(delivery_id)
            return delivery

        def rollback() -> None:
            for item in inserted:
                self._destinations.get(destination_id, {}).pop(item, None)

        return self._perform(context, effect=EffectType.TRANSMITS, operation="send_to_simulated_destination",
                             source=file.resource_id, destination=destination_identity,
                             classification=file.classification,
                             metadata={"destination_id": destination_identity, "delivery_id": delivery_id,
                                       "adversarial_fixture": adversarial_fixture_override},
                             work=work, rollback=rollback)

    def deliveries(self, destination_id: str) -> list[SimulatedDelivery]:
        return [copy.deepcopy(item) for item in self._destinations.get(destination_id, {}).values()]

    def is_external(self, destination_id: str) -> bool:
        return self._is_external.get(destination_id, False)
