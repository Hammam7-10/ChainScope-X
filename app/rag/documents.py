"""Local policy-document parsing and deterministic, attributed chunking."""
from __future__ import annotations

import hashlib
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.schemas.contracts import Classification


class PolicyDocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    version: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=500)
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}(?:-[A-Za-z0-9]+)*$")
    policy_id: str | None = Field(default=None, max_length=160)
    access_classification: Classification = Classification.INTERNAL
    document_status: str = Field(default="ACTIVE", pattern=r"^(ACTIVE|OBSOLETE)$")
    effective_date: str | None = Field(default=None, max_length=80)
    page: int | None = Field(default=None, ge=1)
    policy_rule_json: str | None = None

    @field_validator("source")
    @classmethod
    def source_is_not_a_local_absolute_path(cls, value: str) -> str:
        if value.startswith(("/", "\\")) or ".." in Path(value).parts:
            raise ValueError("source must be a safe, portable attribution path")
        return value


@dataclass(frozen=True)
class ParsedPolicyDocument:
    metadata: PolicyDocumentMetadata
    body: str
    content_sha256: str
    sections: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PolicyChunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]


def _iso_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def detect_language(text: str, fallback: str = "en") -> str:
    letters = [char for char in text if unicodedata.category(char).startswith("L")]
    if not letters:
        return fallback
    arabic = sum("\u0600" <= char <= "\u06ff" for char in letters)
    return "ar" if arabic / len(letters) >= 0.08 else fallback


def _extract_sections(body: str) -> tuple[tuple[str, str], ...]:
    sections: list[tuple[str, str]] = []
    current_title = "document"
    current_lines: list[str] = []

    def flush() -> None:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append((current_title, text))

    for line in body.splitlines():
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading:
            flush()
            current_title = heading.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    flush()
    return tuple(sections) or (("document", body.strip()),)


def parse_policy_document(path: str | Path) -> ParsedPolicyDocument:
    """Read UTF-8 Markdown/TXT, parse optional TOML front matter, and preserve source fields."""
    path = Path(path)
    if path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("Only UTF-8 Markdown and text policy files are supported")
    raw_bytes = path.read_bytes()
    raw = raw_bytes.decode("utf-8")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    header: dict[str, Any] = {}
    body = normalized
    if normalized.startswith("+++\n"):
        delimiter = normalized.find("\n+++\n", 4)
        if delimiter < 0:
            raise ValueError("TOML front matter is not closed")
        header = tomllib.loads(normalized[4:delimiter])
        body = normalized[delimiter + 5:]
    inferred_language = detect_language(body)
    raw_metadata = {
        "document_id": header.get("document_id", path.stem),
        "version": header.get("version", "1.0"),
        "source": header.get("source", path.name),
        "language": header.get("language", inferred_language),
        "policy_id": header.get("policy_id"),
        "access_classification": header.get("access_classification", "INTERNAL"),
        "document_status": header.get("document_status", "ACTIVE"),
        "effective_date": _iso_value(header.get("effective_date")),
        "page": header.get("page"),
        "policy_rule_json": header.get("policy_rule_json"),
    }
    metadata = PolicyDocumentMetadata.model_validate(raw_metadata)
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return ParsedPolicyDocument(metadata, body.strip(), content_hash, _extract_sections(body))


def chunk_policy_document(document: ParsedPolicyDocument, *, max_words: int = 72,
                          overlap_words: int = 10) -> tuple[PolicyChunk, ...]:
    if max_words < 16 or overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("Chunk sizing must use max_words >= 16 and 0 <= overlap_words < max_words")
    chunks: list[PolicyChunk] = []
    for section, section_text in document.sections:
        words = section_text.split()
        start = 0
        while start < len(words):
            end = min(start + max_words, len(words))
            body = " ".join(words[start:end]).strip()
            text = f"{section}\n{body}" if section != "document" else body
            material = "|".join((document.metadata.document_id,
                                 document.metadata.version, str(len(chunks)), text))
            chunk_id = "chunk:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
            language = detect_language(text, document.metadata.language)
            metadata: dict[str, Any] = {
                "document_id": document.metadata.document_id,
                "version": document.metadata.version,
                "source": document.metadata.source,
                "section": section[:240],
                "chunk_id": chunk_id,
                "language": language,
                "policy_id": document.metadata.policy_id or "",
                "access_classification": document.metadata.access_classification.value,
                "document_status": document.metadata.document_status,
                "content_sha256": document.content_sha256,
                "chunk_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
            if document.metadata.page is not None:
                metadata["page"] = document.metadata.page
            if document.metadata.effective_date is not None:
                metadata["effective_date"] = document.metadata.effective_date
            chunks.append(PolicyChunk(chunk_id, text, metadata))
            if end >= len(words):
                break
            start = end - overlap_words
    return tuple(chunks)
