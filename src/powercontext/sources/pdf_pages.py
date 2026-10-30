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

"""Full-document PDF parsing with page-level evidence retrieval."""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from typing import Any, ClassVar
from urllib.parse import quote, unquote

from pydantic import BaseModel

from powercontext.artifacts import MemoryCitation
from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    TextEvidence,
)
from powercontext.sources.models import Source, SourceMaterialization

PDF_PAGE_SOURCE_NAME = "pdf-page"
_PDF_IDENTITY_PREFIX = "pdf:"
_QUERY_TOKEN = re.compile(r"[a-z]+|\d+")
_YEAR_TOKEN = re.compile(r"(19|20)\d{2}")
_STOP_TOKENS = frozenset([
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "at",
    "by",
    "for",
    "from",
    "with",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "what",
    "which",
    "who",
    "how",
    "why",
    "when",
    "where",
    "did",
    "do",
    "does",
    "can",
    "could",
    "should",
    "would",
    "it",
    "its",
    "their",
    "there",
    "that",
    "this",
    "these",
    "those",
    "we",
    "our",
    "you",
    "your",
    "us",
    "has",
    "have",
    "had",
    "not",
    "no",
    "than",
    "then",
    "into",
    "about",
    "over",
    "under",
    "during",
    "please",
    "give",
    "list",
    "much",
    "many",
    "any",
    "if",
    "like",
    "state",
    "explain",
    "useful",
    "based",
    "measure",
    "relevant",
    "indicate",
    "provide",
    "given",
    "also",
    "more",
    "most",
    "some",
    "other",
    "because",
    "while",
    "might",
    "must",
    "shall",
    "may",
    "need",
    "needs",
    "using",
    "use",
    "used",
    "versus",
    "per",
    "whether",
    "such",
    "each",
    "both",
    "all",
    "only",
])
_PAGE_TYPE_VOCAB: dict[str, frozenset[str]] = {
    "income": frozenset([
        "income",
        "operation",
        "operating",
        "revenue",
        "expense",
        "earning",
        "profit",
        "margin",
        "gross",
        "ebit",
        "tax",
        "statement",
    ]),
    "balance": frozenset([
        "balance",
        "sheet",
        "asset",
        "liability",
        "equity",
        "inventory",
        "receivable",
        "payable",
        "goodwill",
        "liquidity",
    ]),
    "cashflow": frozenset([
        "cash",
        "flow",
        "investing",
        "financing",
        "dividend",
        "depreciation",
        "amortization",
        "expenditure",
    ]),
    "legal": frozenset(["legal", "proceeding", "litigation", "lawsuit", "contingency", "claim", "dispute"]),
    "segment": frozenset([
        "segment",
        "reportable",
        "geographic",
        "geography",
        "business",
        "customer",
        "division",
        "distributor",
        "category",
        "franchise",
        "region",
    ]),
    "liquidity": frozenset(["liquidity", "capital", "resource", "covenant", "facility"]),
}
_QUESTION_TYPE_HINTS: dict[str, frozenset[str]] = {
    "income": frozenset([
        "margin",
        "profitability",
        "profitable",
        "revenue",
        "growth",
        "income",
        "earning",
        "profit",
        "operating",
        "gross",
        "ebit",
        "eps",
        "diluted",
        "sale",
        "expense",
        "cogs",
        "rd",
        "tax",
        "taxes",
    ]),
    "balance": frozenset([
        "liquidity",
        "ratio",
        "quick",
        "current",
        "asset",
        "liability",
        "debt",
        "equity",
        "leverage",
        "solvency",
        "working",
        "inventory",
        "receivable",
        "cash",
        "balance",
    ]),
    "cashflow": frozenset([
        "cash",
        "flow",
        "capex",
        "expenditure",
        "dividend",
        "buyback",
        "repurchase",
        "investing",
        "financing",
        "depreciation",
        "amortization",
    ]),
    "legal": frozenset([
        "legal",
        "battle",
        "proceeding",
        "litigation",
        "lawsuit",
        "dispute",
        "investigation",
        "claim",
        "regulatory",
        "violation",
    ]),
    "segment": frozenset([
        "segment",
        "division",
        "geographic",
        "geography",
        "businesses",
        "customer",
        "concentration",
        "category",
        "region",
        "franchise",
        "product",
        "service",
        "supplier",
    ]),
    "liquidity": frozenset(["liquidity", "covenant", "credit", "facility", "borrowing"]),
}


class PDFDocumentInput(BaseModel):
    """A complete original PDF awaiting full-page extraction."""

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """One extracted physical page bound to its document identity."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageSource(Source):
    """A captured PDF page whose identity covers the document revision."""

    source_id: str
    document_id: str
    document_sha256: str
    page_number: int
    text: str


def pdf_page_source_id(document_id: str, document_sha256: str, page_number: int, /) -> str:
    """Build the revision-stable page identity from its immutable components."""

    identity = f"{_PDF_IDENTITY_PREFIX}{quote(document_id, safe='')}:{document_sha256}:{page_number}"
    if len(identity) > MAX_SOURCE_ID_LENGTH:
        message = f"pdf page source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters"
        raise ValueError(message)
    return identity


def parse_pdf_document(value: PDFDocumentInput, /) -> tuple[PDFPageInput, ...]:
    """Extract every physical page of one document, or fail without partial output."""

    document_id = value.document_id
    if not isinstance(document_id, str) or not document_id.strip():
        message = "document_id must not be empty or pure whitespace"
        raise ValueError(message)
    document_sha256 = hashlib.sha256(value.content).hexdigest()
    return tuple(
        PDFPageInput(
            document_id=document_id,
            document_sha256=document_sha256,
            page_number=number,
            text=text,
        )
        for number, text in enumerate(_extract_pages(value.content), start=1)
    )


def _reject_encrypted_pdf() -> None:
    message = "PDF requires a non-empty password"
    raise ValueError(message)


def _extract_pages(content: bytes, /) -> list[str]:
    try:
        from pypdf import PasswordType, PdfReader
    except ModuleNotFoundError as error:
        if error.name != "pypdf":
            raise
        message = "PDF parsing requires the PDF extra; install powercontext[pdf]"
        raise ValueError(message) from error

    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and reader.decrypt("") is PasswordType.NOT_DECRYPTED:
            _reject_encrypted_pdf()
        return [page.extract_text() or "" for page in reader.pages]
    except ValueError:
        raise
    except Exception as error:
        message = f"unreadable PDF document: {type(error).__name__}"
        raise ValueError(message) from error


class PDFPageSourceAdapter:
    """Resolve and read one page-level PDF Source."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        source_id = pdf_page_source_id(value.document_id, value.document_sha256, value.page_number)
        return PDFPageSource(
            name=source_id,
            materialization=SourceMaterialization.CAPTURED,
            source_id=source_id,
            document_id=value.document_id,
            document_sha256=value.document_sha256,
            page_number=value.page_number,
            text=value.text,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class PDFPageTextEvidenceProjection:
    """Project one page as textual evidence with its document and page metadata."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: ClassVar[type[BaseModel]] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.source_id,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(
    PDFPageSourceAdapter(),
    version="1",
    projections=(PDFPageTextEvidenceProjection(),),
)


def _stem(token: str, /) -> str:
    """Collapse frequent plural morphology without a real stemmer."""

    if token.isdigit() or len(token) < 4:
        return token
    if token.endswith("ies"):
        return f"{token[:-3]}y"
    if (
        token.endswith("ses")
        or token.endswith("xes")
        or token.endswith("zes")
        or token.endswith("ches")
        or token.endswith("shes")
    ):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and not token.endswith("us"):
        return token[:-1]
    return token


_PAGE_TYPE_STEMS: dict[str, frozenset[str]] = {
    name: frozenset(_stem(stem) for stem in vocabulary) for name, vocabulary in _PAGE_TYPE_VOCAB.items()
}
_QUESTION_TYPE_STEMS: dict[str, frozenset[str]] = {
    name: frozenset(_stem(stem) for stem in hints) for name, hints in _QUESTION_TYPE_HINTS.items()
}


def _question_types(question_stems: set[str], /) -> set[str]:
    """Map question vocabulary onto the statement types it asks about."""

    return {name for name, hints in _QUESTION_TYPE_STEMS.items() if question_stems & hints}


def _tokens(text: str, /) -> Counter[str]:
    return Counter(_QUERY_TOKEN.findall(text.lower()))


def _content_terms(question: str, /) -> list[str]:
    """Ordered content tokens of one question, skipping boilerplate words."""

    seen: set[str] = set()
    terms: list[str] = []
    for token in _QUERY_TOKEN.findall(question.lower()):
        if token in _STOP_TOKENS or len(token) < 2:
            continue
        if token not in seen:
            seen.add(token)
            terms.append(token)
    return terms


def _page_location(source_id: str, /) -> tuple[str, str, int] | None:
    """Recover (document_id, page_number) from this module's page identity."""

    if not source_id.startswith(_PDF_IDENTITY_PREFIX):
        return None
    head, separator, page = source_id.rpartition(":")
    if not separator or not page.isdigit():
        return None
    encoded = head.removeprefix(_PDF_IDENTITY_PREFIX)
    _, _, sha = encoded.rpartition(":")
    if len(sha) != 64 or any(character not in "0123456789abcdef" for character in sha):
        return None
    document_part = encoded[: len(encoded) - 65]
    return unquote(document_part), sha, int(page)


def _page_text(entry_text: str, /) -> str:
    """Strip the DOCUMENT_ID heading used by the pdf-page projection."""

    _heading, separator, body = entry_text.partition("\n")
    return body if separator else entry_text


def _relevance(
    question_terms: list[str],
    page_tokens: Counter[str],
    title_stems: set[str],
    pool_size: int,
    document_frequency: Counter[str],
    question_types: set[str],
    /,
) -> float:
    """Score one page with stemmed IDF evidence plus statement-type affinity."""

    weighted: dict[str, float] = {}
    for term in question_terms:
        canonical = _stem(term)
        weighted[canonical] = weighted.get(canonical, 0.0) + 1.0
    page_stems = {_stem(token) for token in page_tokens}
    score = 0.0
    matched = 0
    rare_matches = 0
    for canonical, wanted in weighted.items():
        frequency = sum(count for token, count in page_tokens.items() if _stem(token) == canonical)
        if not frequency:
            continue
        matched += 1
        idf = math.log(1.0 + pool_size / (1.0 + document_frequency.get(canonical, 0)))
        if idf > 2.0:
            rare_matches += 1
        score += idf * (frequency / (frequency + 1.2)) * wanted
    if weighted:
        coverage = matched / len(weighted)
        for index in range(len(question_terms) - 1):
            left, right = _stem(question_terms[index]), _stem(question_terms[index + 1])
            if left in page_stems and right in page_stems:
                score += 0.75
        score *= 0.4 + 0.6 * coverage
    score += min(rare_matches * 1.5, 3.0)
    years = {term for term in question_terms if _YEAR_TOKEN.fullmatch(term)}
    if years and all(year in page_tokens for year in years):
        score += 0.5
    score += _statement_type_score(question_types, page_stems, title_stems)
    return score


def _statement_type_score(question_types: set[str], page_stems: set[str], title_stems: set[str]) -> float:
    score = 0.0
    for question_type in question_types:
        vocabulary = _PAGE_TYPE_STEMS[question_type]
        present = sum(1 for stem in vocabulary if stem in page_stems)
        if present < 2:
            continue
        score += 4.0 * min(present / max(len(vocabulary) * 0.5, 1.0), 1.0)
        if sum(1 for stem in vocabulary if stem in title_stems) >= 2:
            score += 4.0
    return score


async def search_pdf_pages(
    memory,
    question: str,
    limit: int = 10,
) -> tuple[MemoryCitation, ...]:
    """Return exact page citations answering one natural-language question.

    Candidates come from the scoped Memory's public entry listing, are scored
    offline against the question, and the strongest pages are completed with
    same-document adjacent pages because evidence clusters on neighboring
    statement pages. Every returned citation is a real stored entry.
    """

    if not isinstance(question, str) or not question.strip():
        message = "question must be non-empty text"
        raise ValueError(message)
    if limit < 1:
        message = "limit must be positive"
        raise ValueError(message)

    listing = await memory.list()
    records = [record for record in listing.entries if record.state == "active"]
    if not records:
        return ()

    terms = _content_terms(question)
    question_types = _question_types({_stem(term) for term in terms})
    token_counts = [
        (record, _tokens(page_body), {_stem(token) for token in _QUERY_TOKEN.findall(page_body.lower())[:20]})
        for record, page_body in ((record, _page_text(record.entry.text)) for record in records)
    ]
    pool_size = max(len(token_counts), 1)
    document_frequency: Counter[str] = Counter()
    for _record, tokens, _title_stems in token_counts:
        document_frequency.update({_stem(token) for token in tokens})

    scored: list[tuple[float, Any, tuple[str, str, int] | None]] = []
    for record, tokens, title_stems in token_counts:
        score = _relevance(terms, tokens, title_stems, pool_size, document_frequency, question_types)
        locations = {
            _page_location(reference.source_id)
            for reference in record.entry.sources
            if reference.source_type == PDF_PAGE_SOURCE_NAME
        }
        locations.discard(None)
        scored.append((score, record, min(locations) if locations else None))
    scored.sort(key=lambda item: item[0], reverse=True)

    selected = _select_pages(scored, limit)
    return tuple(
        MemoryCitation(
            memory_ref=record.memory_ref,
            entry_id=record.entry.entry_id,
            entry_version_id=record.entry.entry_version_id,
        )
        for _score, record, _location in selected[:limit]
    )


def _select_pages(scored: list[tuple[float, Any, tuple[str, str, int] | None]], limit: int):
    by_location = {location: (score, record) for score, record, location in scored if location is not None}
    anchor_slots = max(min((limit + 1) // 2, len(scored)), 1)
    selected: list[tuple[float, Any, tuple[str, str, int] | None]] = []
    seen_locations: set[tuple[str, str, int]] = set()
    anchor_locations: list[tuple[str, str, int]] = []
    for candidate in scored:
        if len(selected) >= anchor_slots:
            break
        if candidate[2] is None or candidate[2] in seen_locations:
            continue
        selected.append(candidate)
        seen_locations.add(candidate[2])
        anchor_locations.append(candidate[2])
    neighbors = _neighbor_pages(anchor_locations, seen_locations, by_location)
    selected_ids = {id(record) for _score, record, _location in selected}
    for candidate in [*neighbors, *scored]:
        if len(selected) >= limit:
            break
        if id(candidate[1]) in selected_ids:
            continue
        if candidate[2] is not None and candidate[2] in seen_locations:
            continue
        selected.append(candidate)
        selected_ids.add(id(candidate[1]))
        if candidate[2] is not None:
            seen_locations.add(candidate[2])
    return selected


def _neighbor_pages(anchor_locations, seen_locations, by_location):
    neighbors: list[tuple[float, Any, tuple[str, str, int] | None]] = []
    queued_locations: set[tuple[str, str, int]] = set()
    for index, (document_id, document_sha256, page_number) in enumerate(anchor_locations):
        window = (1, -1, 2, -2, 3, -3) if index < 5 else (1, -1, 2, -2)
        for delta in window:
            location = (document_id, document_sha256, page_number + delta)
            if location in seen_locations or location in queued_locations:
                continue
            found = by_location.get(location)
            if found is None:
                continue
            neighbors.append((found[0], found[1], location))
            queued_locations.add(location)
    neighbors.sort(key=lambda item: item[0], reverse=True)
    return neighbors


__all__ = [
    "PDF_PAGE_SOURCE_DEFINITION",
    "PDFDocumentInput",
    "PDFPageInput",
    "PDFPageSource",
    "parse_pdf_document",
    "pdf_page_source_id",
    "search_pdf_pages",
]
