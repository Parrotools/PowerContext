"""Review coach routes — adaptive study recommendations powered by PowerContext memory."""

import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    ReviewResponse,
    ReviewRecommendation,
    TopicStatus,
    MasteryLevel,
    MarkMasteryRequest,
    SearchResult,
)
from app.services import powercontext_service, seekdb_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/status/{user_id}", response_model=ReviewResponse)
async def get_review_status(user_id: str):
    """
    Get the user's learning dashboard:
    - All tracked topics with mastery levels
    - Topics due for review (spaced repetition)
    - Personalized study recommendations
    """
    try:
        learning_state = await powercontext_service.get_user_learning_state(user_id)
        due_topics = await powercontext_service.get_due_for_review(user_id)
        weak_topics = await powercontext_service.get_weak_topics(user_id)
    except Exception as e:
        logger.warning(f"PowerContext unavailable: {e}")
        return ReviewResponse(
            user_id=user_id,
            topics=[],
            recommendations=[],
            study_summary="记忆服务暂不可用，请先确认 PowerContext 已启动。",
        )

    topics = [
        TopicStatus(
            topic=s.get("topic", ""),
            mastery=MasteryLevel(s.get("mastery", "unseen")),
            last_reviewed=s.get("last_reviewed"),
            review_count=s.get("review_count", 0),
            next_review=s.get("next_review"),
            weakness_reason=s.get("note"),
        )
        for s in learning_state
    ]

    recommendations: list[ReviewRecommendation] = []

    for item in due_topics[:5]:
        topic_name = item.get("topic", "")
        try:
            materials = await seekdb_service.hybrid_search(query=topic_name, limit=3)
        except Exception:
            materials = []
        recommendations.append(ReviewRecommendation(
            topic=topic_name,
            priority="high" if item.get("mastery") == "needs_review" else "medium",
            reason="距离上次复习已超过计划间隔，建议复习巩固",
            suggested_materials=[SearchResult(**m) for m in materials],
        ))

    for item in weak_topics[:3]:
        topic_name = item.get("topic", "")
        if any(r.topic == topic_name for r in recommendations):
            continue
        try:
            materials = await seekdb_service.hybrid_search(query=topic_name, limit=3)
        except Exception:
            materials = []
        recommendations.append(ReviewRecommendation(
            topic=topic_name,
            priority="high",
            reason=item.get("note", "薄弱知识点，需要重点攻克"),
            suggested_materials=[SearchResult(**m) for m in materials],
        ))

    mastered = sum(1 for s in learning_state if s.get("mastery") == "mastered")
    total = len(learning_state)
    summary = (
        f"共追踪 {total} 个知识点，已掌握 {mastered} 个，"
        f"当前有 {len(due_topics)} 个需要复习。"
    )

    return ReviewResponse(
        user_id=user_id,
        topics=topics,
        recommendations=recommendations,
        study_summary=summary,
    )


@router.post("/mastery")
async def mark_mastery(req: MarkMasteryRequest):
    """Update mastery level for a topic (user self-assessment or system-detected)."""
    result = await powercontext_service.update_topic_mastery(
        user_id=req.user_id,
        topic=req.topic,
        mastery=req.mastery.value,
        note=req.note,
    )
    if result is None:
        raise HTTPException(503, "PowerContext memory service unavailable")
    return {"ok": True, "topic": req.topic, "mastery": req.mastery.value, "updated": True}


@router.get("/memory/{user_id}")
async def get_learning_memory(user_id: str):
    """Get all memory entries related to a user's learning journey."""
    try:
        memories = await powercontext_service.search_memory(
            query=f"learning progress user {user_id}",
            limit=20,
        )
        return {"user_id": user_id, "memories": memories}
    except Exception as e:
        logger.warning(f"PowerContext unavailable: {e}")
        return {"user_id": user_id, "memories": [], "note": "Memory service unavailable"}
