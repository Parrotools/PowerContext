"""FastAPI application entry point for 知序 (ZhiXu) Learning Assistant."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.services import seekdb_service
from app.services.seekdb_service import SeekDBUnavailableError
from app.routers import knowledge, chat, review

logger = logging.getLogger(__name__)

_seekdb_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _seekdb_ready
    try:
        seekdb_service.init_client()
        _seekdb_ready = True
        logger.info("Knowledge base (SQLite + sqlite-vec) initialized")
    except Exception as e:
        logger.warning(f"Database init failed: {e} — data operations will return 503")
    yield
    if _seekdb_ready:
        seekdb_service.close_client()


app = FastAPI(
    title="知序 — 智能学习助手",
    description="越用越懂你的个人学习助手，基于 SeekDB 混合检索 + PowerContext 记忆引擎",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(SeekDBUnavailableError)
async def seekdb_unavailable_handler(request: Request, exc: SeekDBUnavailableError):
    return JSONResponse(status_code=503, content={
        "error": "service_unavailable",
        "detail": str(exc),
        "hint": "Please ensure SeekDB is running. See README.md for setup instructions.",
    })


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={
        "error": "internal_error",
        "detail": str(exc),
    })

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(knowledge.router)
app.include_router(chat.router)
app.include_router(review.router)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "zhixu-learning-assistant",
        "seekdb": "connected (sqlite-vec)" if _seekdb_ready else "not available",
        "powercontext": settings.POWERCONTEXT_URL,
        "llm": "configured" if settings.LLM_API_KEY else "not configured (demo mode)",
    }
