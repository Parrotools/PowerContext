# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Row-level CSV capture with exact raw-record lookups."""

from __future__ import annotations

import csv
import io
import json
from typing import ClassVar
from urllib.parse import quote

from pydantic import BaseModel

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, AdapterSourceDefinition, TextEvidence
from powercontext.sources.models import Source, SourceMaterialization

CSV_ROW_SOURCE_NAME = "csv-row"
_CSV_IDENTITY_PREFIX = "csv:"
_UTF8_BOM = "\ufeff"


class CSVDocumentInput(BaseModel):
    """A complete offline CSV document awaiting row-level capture."""

    document_id: str
    primary_key: str
    content: bytes


class CSVRowInput(BaseModel):
    """One captured data row with its document identity and original fields."""

    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


class CSVRowSource(Source):
    """A captured CSV row whose identity survives reordering and non-key edits."""

    source_id: str
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


def csv_row_source_id(document_id: str, primary_key_value: str) -> str:
    """Build the stable row identity, percent-encoding both components."""

    if not document_id or document_id.strip() != document_id:
        message = "document_id must be a non-empty string without leading or trailing whitespace"
        raise ValueError(message)
    identity = f"{_CSV_IDENTITY_PREFIX}{quote(document_id, safe='')}:{quote(primary_key_value, safe='')}"
    if len(identity) > MAX_SOURCE_ID_LENGTH:
        message = f"csv row source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters"
        raise ValueError(message)
    return identity


def parse_csv_document(value: CSVDocumentInput, /) -> tuple[CSVRowInput, ...]:
    """Parse and validate the whole document before returning any rows."""

    document_id = value.document_id
    if not document_id or document_id.strip() != document_id:
        message = "document_id must be a non-empty string without leading or trailing whitespace"
        raise ValueError(message)
    if not value.primary_key:
        message = "primary_key must be a non-empty column name"
        raise ValueError(message)

    try:
        text = value.content.decode("utf-8")
    except UnicodeDecodeError as error:
        message = "document content must be valid UTF-8"
        raise ValueError(message) from error
    if text.startswith(_UTF8_BOM):
        text = text.removeprefix(_UTF8_BOM)

    try:
        records = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as error:
        message = f"malformed CSV document: {error}"
        raise ValueError(message) from error
    if not records or not records[0]:
        message = "document must contain a header record"
        raise ValueError(message)

    return _csv_rows(records, document_id, value.primary_key)


def _csv_rows(records: list[list[str]], document_id: str, primary_key: str) -> tuple[CSVRowInput, ...]:
    header = records[0]
    for field in header:
        if not field or not field.strip():
            message = "header fields must be non-empty and not pure whitespace"
            raise ValueError(message)
    if len(set(header)) != len(header):
        message = "header fields must be unique"
        raise ValueError(message)
    if primary_key not in header:
        message = f"primary_key {primary_key!r} must name one header column"
        raise ValueError(message)
    key_index = header.index(primary_key)
    width = len(header)

    rows: list[CSVRowInput] = []
    seen_keys: set[str] = set()
    for record in records[1:]:
        if not record:
            continue
        if len(record) != width:
            message = "data record width must match the header"
            raise ValueError(message)
        primary_key_value = record[key_index]
        if not primary_key_value.strip():
            message = "primary key values must not be empty or pure whitespace"
            raise ValueError(message)
        if primary_key_value in seen_keys:
            message = f"duplicate primary key value {primary_key_value!r}"
            raise ValueError(message)
        seen_keys.add(primary_key_value)
        rows.append(
            CSVRowInput(
                document_id=document_id,
                primary_key=primary_key,
                primary_key_value=primary_key_value,
                columns=tuple(header),
                values=tuple(record),
            )
        )
    return tuple(rows)


class CSVRowSourceAdapter:
    """Resolve and read one row-level CSV Source."""

    input_class = CSVRowInput
    name = CSV_ROW_SOURCE_NAME
    source_class = CSVRowSource

    async def resolve(self, value: CSVRowInput, /) -> CSVRowSource:
        source_id = csv_row_source_id(value.document_id, value.primary_key_value)
        return CSVRowSource(
            name=source_id,
            materialization=SourceMaterialization.CAPTURED,
            source_id=source_id,
            document_id=value.document_id,
            primary_key=value.primary_key,
            primary_key_value=value.primary_key_value,
            columns=value.columns,
            values=value.values,
        )

    async def read(self, source: CSVRowSource, /) -> CSVRowInput:
        return CSVRowInput(
            document_id=source.document_id,
            primary_key=source.primary_key,
            primary_key_value=source.primary_key_value,
            columns=source.columns,
            values=source.values,
        )


class CSVRowTextEvidenceProjection:
    """Project one row as textual evidence with exact raw-record metadata."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = CSVRowSource
    output_class: ClassVar[type[BaseModel]] = TextEvidence

    def project(self, source: CSVRowSource, /) -> TextEvidence:
        row = dict(zip(source.columns, source.values, strict=True))
        return TextEvidence(
            source_type=CSV_ROW_SOURCE_NAME,
            source_id=source.source_id,
            content=json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            metadata={
                "document_id": source.document_id,
                "primary_key": source.primary_key,
                "primary_key_value": source.primary_key_value,
                "columns": list(source.columns),
                "row": row,
            },
        )


CSV_ROW_SOURCE_DEFINITION = AdapterSourceDefinition(
    CSVRowSourceAdapter(),
    version="1",
    projections=(CSVRowTextEvidenceProjection(),),
)

__all__ = [
    "CSV_ROW_SOURCE_DEFINITION",
    "CSVDocumentInput",
    "CSVRowInput",
    "CSVRowSource",
    "csv_row_source_id",
    "parse_csv_document",
]
