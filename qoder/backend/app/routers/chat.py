"""Chat routes — intelligent Q&A combining SeekDB retrieval + PowerContext memory."""

import logging
from fastapi import APIRouter
from app.models.schemas import ChatRequest, ChatResponse, SearchResult
from app.services import seekdb_service, powercontext_service, llm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/message", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Core chat endpoint:
    1. Search SeekDB for relevant knowledge chunks
    2. Recall user's learning state from PowerContext
    3. Build prompt with retrieved context + memory
    4. Call LLM for answer
    5. Save interaction to PowerContext for future recall
    """
    search_results = await seekdb_service.hybrid_search(query=req.message, limit=5)

    learning_state = []
    memory_summary = None
    try:
        learning_state = await powercontext_service.get_user_learning_state(req.user_id)
        memory_ctx = await powercontext_service.prepare_context(req.user_id, req.message)
        if memory_ctx and memory_ctx.get("content"):
            memory_summary = memory_ctx["content"]
    except Exception as e:
        logger.warning(f"PowerContext unavailable, continuing without memory: {e}")

    messages = llm_service.build_chat_prompt(
        user_message=req.message,
        retrieved_context=search_results,
        memory_context=memory_summary,
        learning_state=learning_state,
    )

    answer = await llm_service.chat_completion(messages)

    try:
        await powercontext_service.capture_chat_interaction(
            user_msg=req.message,
            assistant_msg=answer,
            topic=_extract_topic(search_results),
            user_id=req.user_id,
        )
    except Exception as e:
        logger.warning(f"Failed to save chat interaction: {e}")

    return ChatResponse(
        answer=answer,
        sources=[SearchResult(**r) for r in search_results],
        memory_context=memory_summary,
        session_id=req.session_id,
    )


@router.get("/history/{user_id}")
async def get_chat_history(user_id: str):
    """Retrieve past chat interactions from PowerContext memory."""
    try:
        memories = await powercontext_service.search_memory(
            query=f"user:{user_id} chat interaction",
            limit=20,
        )
        return {"user_id": user_id, "history": memories}
    except Exception as e:
        logger.warning(f"PowerContext unavailable: {e}")
        return {"user_id": user_id, "history": [], "note": "Memory service unavailable"}


def _extract_topic(results: list[dict]) -> str:
    """Extract a rough topic label from search results."""
    if not results:
        return ""
    titles = [r.get("title", "") for r in results[:3]]
    return " | ".join(t for t in titles if t)
