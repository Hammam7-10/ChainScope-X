"""Evidence-backed capability graph construction and cycle-safe path enumeration."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from app.core.schemas.contracts import (
    CapabilityPath, Classification, EffectType, GraphEdge, GraphEdgeType, GraphNode,
    ObservedEffect, highest_classification,
)


@dataclass(frozen=True)
class GraphBuildResult:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    paths: tuple[CapabilityPath, ...]
    issues: tuple[str, ...]
    truncated: bool = False
    truncation_reasons: tuple[str, ...] = ()


class CapabilityGraphBuilder:
    """Build one graph per execution; no inference from prose, names, or timing."""

    def __init__(self, *, max_depth: int = 16, max_paths: int = 512) -> None:
        if max_depth < 1 or max_paths < 1:
            raise ValueError("max_depth and max_paths must be positive integers")
        self.max_depth = max_depth
        self.max_paths = max_paths

    @staticmethod
    def _resource_node_type(resource_id: str) -> str | None:
        if resource_id.startswith(("asset:", "dataset:", "file:", "stored:")):
            return "ASSET"
        if resource_id.startswith("report:"):
            return "TRANSFORMATION"
        if resource_id.startswith("destination:"):
            return "DESTINATION"
        return None

    def build(self, execution_id: str, events: Iterable[ObservedEffect]) -> GraphBuildResult:
        issues: list[str] = []
        node_by_id: dict[str, GraphNode] = {}
        edge_by_key: dict[tuple[str, str, str, str], GraphEdge] = {}

        def add_resource(resource_id: str | None, classification: Classification) -> str | None:
            if not resource_id or resource_id == "resource:unresolved":
                return None
            node_type = self._resource_node_type(resource_id)
            if node_type is None:
                issues.append("graph_resource_identity_unrecognized")
                return None
            node_id = f"{execution_id}::resource::{resource_id}"
            existing = node_by_id.get(node_id)
            if existing is None:
                node_by_id[node_id] = GraphNode(
                    node_id=node_id, node_type=node_type, resource_id=resource_id,
                    execution_id=execution_id, classification=classification,
                )
            elif existing.classification != classification:
                node_by_id[node_id] = existing.model_copy(update={
                    "classification": highest_classification(existing.classification, classification)
                })
            return node_id

        def add_tool(event: ObservedEffect, *, isolated_transform: bool = False) -> str:
            suffix = f"::unlinked::{event.event_id}" if isolated_transform else ""
            node_id = f"{execution_id}::tool::{event.invocation_id}{suffix}"
            node_by_id.setdefault(node_id, GraphNode(
                node_id=node_id, node_type="TOOL", resource_id=event.tool_id,
                execution_id=execution_id, classification=None,
            ))
            return node_id

        def add_edge(source_id: str | None, target_id: str | None, edge_type: GraphEdgeType,
                     event: ObservedEffect) -> None:
            if source_id is None or target_id is None:
                return
            if not event.evidence:
                issues.append("graph_edge_without_evidence")
                return
            key = (source_id, target_id, edge_type.value, event.event_id)
            edge = edge_by_key.get(key)
            if edge is None:
                material = "|".join((execution_id, *key))
                edge_id = "edge:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
                edge_by_key[key] = GraphEdge(
                    edge_id=edge_id, source_node_id=source_id, target_node_id=target_id,
                    edge_type=edge_type, execution_id=execution_id, event_ids=[event.event_id],
                    classification=event.classification,
                    evidence_ids=sorted({item.evidence_id for item in event.evidence}),
                    invocation_ids=[event.invocation_id],
                )

        all_events = tuple(events)
        successful = [event for event in all_events
                      if event.execution_id == execution_id and event.outcome == "SUCCESS"]
        if any(event.execution_id != execution_id for event in all_events):
            issues.append("cross_execution_event_excluded")
        reads_by_invocation: dict[str, set[str]] = {}
        for event in successful:
            if event.effect_type == EffectType.READS and event.source_resource:
                reads_by_invocation.setdefault(event.invocation_id, set()).add(event.source_resource)
        transform_outputs = {
            (event.invocation_id, event.destination_resource)
            for event in successful
            if event.effect_type == EffectType.TRANSFORMS and event.destination_resource
        }

        for event in sorted(successful, key=lambda item: (item.sequence, item.event_id)):
            lineage = event.metadata.get("source_asset_ids") if event.effect_type == EffectType.TRANSFORMS else None
            lineage_shape_valid = (isinstance(lineage, list) and bool(lineage)
                                   and all(isinstance(item, str) and item for item in lineage))
            observed_sources = reads_by_invocation.get(event.invocation_id, set())
            lineage_valid = (lineage_shape_valid and bool(observed_sources)
                             and set(lineage) == observed_sources
                             and event.source_resource in set(lineage))
            tool_id = add_tool(event, isolated_transform=(event.effect_type == EffectType.TRANSFORMS
                                                         and not lineage_valid))
            source_id = add_resource(event.source_resource, event.classification)
            destination_id = add_resource(event.destination_resource, event.classification)

            if event.effect_type in {EffectType.READS, EffectType.SEARCHES}:
                if source_id is None:
                    issues.append("observed_read_without_stable_source")
                else:
                    add_edge(source_id, tool_id, GraphEdgeType(event.effect_type.value), event)
                continue

            if event.effect_type == EffectType.TRANSFORMS:
                if not lineage_shape_valid:
                    issues.append("transformation_lineage_missing")
                elif not lineage_valid:
                    issues.append("transformation_lineage_unverified_against_reads")
                else:
                    for resource_id in dict.fromkeys(lineage):
                        input_node = add_resource(resource_id, event.classification)
                        if input_node is None:
                            issues.append("transformation_lineage_resource_unresolved")
                        else:
                            add_edge(input_node, tool_id, GraphEdgeType.USES, event)
                if destination_id is None:
                    issues.append("transformation_output_unresolved")
                else:
                    add_edge(tool_id, destination_id, GraphEdgeType.TRANSFORMS, event)
                continue

            # A report-to-file CREATE in one invocation continues a recorded transform
            # lineage directly; routing back through the same tool node would make a loop.
            if (event.effect_type == EffectType.CREATES and source_id and destination_id
                    and (event.invocation_id, event.source_resource) in transform_outputs):
                add_edge(source_id, destination_id, GraphEdgeType.CREATES, event)
                continue

            if source_id is not None:
                add_edge(source_id, tool_id, GraphEdgeType.USES, event)
            elif event.source_resource:
                issues.append("effect_source_unresolved")
            if destination_id is not None:
                add_edge(tool_id, destination_id, GraphEdgeType(event.effect_type.value), event)
            elif event.destination_resource:
                issues.append("effect_destination_unresolved")
            if source_id is None and destination_id is None:
                issues.append("effect_has_no_graph_endpoints")

        nodes = tuple(node_by_id[key] for key in sorted(node_by_id))
        edges = tuple(sorted(edge_by_key.values(), key=lambda item: item.edge_id))
        paths, truncation_reasons = self._enumerate_paths(execution_id, nodes, edges)
        issues.extend(truncation_reasons)
        return GraphBuildResult(nodes, edges, paths, tuple(dict.fromkeys(issues)),
                                bool(truncation_reasons), truncation_reasons)

    def _enumerate_paths(self, execution_id: str, nodes: tuple[GraphNode, ...],
                         edges: tuple[GraphEdge, ...]) -> tuple[tuple[CapabilityPath, ...], tuple[str, ...]]:
        node_by_id = {node.node_id: node for node in nodes}
        outgoing: dict[str, list[GraphEdge]] = {}
        for edge in edges:
            if edge.execution_id == execution_id:
                outgoing.setdefault(edge.source_node_id, []).append(edge)
        for items in outgoing.values():
            items.sort(key=lambda item: (item.edge_type.value, item.target_node_id, item.edge_id))

        paths: list[CapabilityPath] = []
        seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        truncation_reasons: set[str] = set()

        def add_path(node_ids: list[str], edge_path: list[GraphEdge]) -> None:
            if not edge_path or len(paths) >= self.max_paths:
                return
            edge_ids = tuple(edge.edge_id for edge in edge_path)
            key = (tuple(node_ids), edge_ids)
            if key in seen:
                return
            seen.add(key)
            event_ids = list(dict.fromkeys(event_id for edge in edge_path for event_id in edge.event_ids))
            classifications = [edge.classification for edge in edge_path]
            endpoint = node_by_id[node_ids[-1]]
            paths.append(CapabilityPath(
                execution_id=execution_id, node_ids=list(node_ids), edge_ids=list(edge_ids),
                event_ids=event_ids,
                source_classification=highest_classification(*classifications),
                destination_id=endpoint.resource_id or endpoint.node_id,
            ))

        def walk(start_id: str, current_id: str, node_path: list[str], edge_path: list[GraphEdge],
                 visited: set[str]) -> None:
            eligible = [edge for edge in outgoing.get(current_id, [])
                        if edge.target_node_id not in visited and edge.target_node_id in node_by_id]
            if len(edge_path) >= self.max_depth:
                if eligible:
                    truncation_reasons.add("graph_depth_limit_reached")
                return
            if len(paths) >= self.max_paths:
                if eligible:
                    truncation_reasons.add("graph_path_limit_reached")
                return
            for index, edge in enumerate(eligible):
                if len(paths) >= self.max_paths:
                    truncation_reasons.add("graph_path_limit_reached")
                    return
                target = edge.target_node_id
                next_nodes = node_path + [target]
                next_edges = edge_path + [edge]
                add_path(next_nodes, next_edges)
                walk(start_id, target, next_nodes, next_edges, visited | {target})
                if len(paths) >= self.max_paths and index < len(eligible) - 1:
                    truncation_reasons.add("graph_path_limit_reached")
                    return

        for start_id in sorted(outgoing):
            walk(start_id, start_id, [start_id], [], {start_id})
        return tuple(paths), tuple(sorted(truncation_reasons))
