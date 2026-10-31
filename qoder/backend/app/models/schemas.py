"""Pydantic models for request/response schemas."""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


# ── Knowledge ──────────────────────────────────────────────

class DocumentCreate(BaseModel):
    title: str
    content: str
    course: str = ""
    tags: list[str] = Field(default_factory=list)
    source_type: str = "markdown"


class DocumentResponse(BaseModel):
    id: int
    title: str
    course: str
    tags: list[str]
    source_type: str
    chunk_count: int
    created_at: str


class SearchResult(BaseModel):
    chunk_id: int
    document_id: int
    title: str
    snippet: str
    course: str
    tags: list[str]
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int


# ── Chat ───────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    user_id: str = "default"


class ChatResponse(BaseModel):
    answer: str
    sources: list[SearchResult]
    memory_context: str | None = None
    session_id: str


# ── Review Coach ───────────────────────────────────────────

class MasteryLevel(str, Enum):
    UNSEEN = "unseen"
    LEARNING = "learning"
    MASTERED = "mastered"
    NEEDS_REVIEW = "needs_review"


class TopicStatus(BaseModel):
    topic: str
    mastery: MasteryLevel
    last_reviewed: str | None = None
    review_count: int = 0
    next_review: str | None = None
    weakness_reason: str | None = None


class ReviewRecommendation(BaseModel):
    topic: str
    priority: str
    reason: str
    suggested_materials: list[SearchResult] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    user_id: str
    topics: list[TopicStatus]
    recommendations: list[ReviewRecommendation]
    study_summary: str


class MarkMasteryRequest(BaseModel):
    topic: str
    mastery: MasteryLevel
    user_id: str = "default"
    note: str = ""
