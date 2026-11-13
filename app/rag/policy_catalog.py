"""Trusted local policy catalog, kept separate from retrieved natural-language passages."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.schemas.contracts import PolicyRule
from app.rag.documents import parse_policy_document


@dataclass(frozen=True)
class PolicyCatalog:
    rules: tuple[PolicyRule, ...]
    source_by_rule_id: dict[str, dict[str, str]]


def load_policy_catalog(directory: str | Path) -> PolicyCatalog:
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError("Trusted local policy source directory does not exist")
    rules: list[PolicyRule] = []
    provenance: dict[str, dict[str, str]] = {}
    paths = sorted(path for path in root.rglob("*")
                   if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"})
    for path in paths:
        document = parse_policy_document(path)
        if document.metadata.document_status != "ACTIVE" or not document.metadata.policy_rule_json:
            continue
        rule = PolicyRule.model_validate_json(document.metadata.policy_rule_json)
        if document.metadata.policy_id != rule.rule_id:
            raise ValueError("Structured policy ID must match its source-document policy_id")
        rules.append(rule)
        provenance[rule.rule_id] = {
            "document_id": document.metadata.document_id,
            "version": document.metadata.version,
            "source": document.metadata.source,
        }
    return PolicyCatalog(tuple(rules), provenance)
