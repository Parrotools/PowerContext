"""Knowledge base routes — CRUD for documents + hybrid search via SeekDB."""

from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import (
    DocumentCreate,
    DocumentResponse,
    SearchResponse,
    SearchResult,
)
from app.services import seekdb_service

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/documents", response_model=DocumentResponse)
async def create_document(doc: DocumentCreate):
    """Import a document into the knowledge base (auto-chunked + embedded in SeekDB)."""
    doc_id = await seekdb_service.insert_document(
        title=doc.title,
        content=doc.content,
        course=doc.course,
        tags=doc.tags,
        source_type=doc.source_type,
    )
    result = await seekdb_service.get_document(doc_id)
    if not result:
        raise HTTPException(500, "Document inserted but could not be retrieved")
    return result


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents():
    """List all documents in the knowledge base."""
    return await seekdb_service.list_documents()


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: int):
    """Get a single document."""
    result = await seekdb_service.get_document(doc_id)
    if not result:
        raise HTTPException(404, "Document not found")
    return result


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    """Delete a document and its chunks."""
    deleted = await seekdb_service.delete_document(doc_id)
    if not deleted:
        raise HTTPException(404, "Document not found")
    return {"ok": True}


@router.get("/search", response_model=SearchResponse)
async def search_knowledge(
    q: str = Query(..., description="Search query (natural language or keywords)"),
    course: str | None = Query(None, description="Filter by course"),
    tags: str | None = Query(None, description="Comma-separated tag filter"),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Hybrid search: vector similarity + full-text matching + structured filter.
    Powered by SeekDB — single SQL query, multi-modal retrieval.
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    results = await seekdb_service.hybrid_search(
        query=q,
        course=course,
        tags=tag_list,
        limit=limit,
    )
    return SearchResponse(
        query=q,
        results=[SearchResult(**r) for r in results],
        total=len(results),
    )
