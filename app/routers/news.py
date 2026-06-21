"""
News Router — public news feed + admin moderation + AI generation.
"""
import asyncio
import logging
from datetime import datetime, timezone, date as dt_date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user, require_admin
from app.models.market_news import MarketNews, NewsStatus
from app.models.user import User
from app.schemas.market_news import (
    MarketNewsCreate,
    MarketNewsRead,
    MarketNewsListItem,
    MarketNewsUpdate,
    MarketNewsStatusUpdate,
    NewsGenerateRequest,
    NewsGenerateResponse,
)
from app.services.ai_news import generate_news_articles, ANTHROPIC_MODEL

logger = logging.getLogger("orbita.news")
router = APIRouter(prefix="/news", tags=["News"])


# ── Public endpoints ──────────────────────────────────────────────

@router.get("/", response_model=List[MarketNewsListItem])
async def list_news(
    category: str | None = Query(None, description="Filter by category"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List published news articles from the last 7 days (public)."""
    seven_days_ago = dt_date.today() - timedelta(days=7)
    stmt = (
        select(MarketNews)
        .where(MarketNews.status == NewsStatus.PUBLISHED.value)
        .where(
            (MarketNews.published_at >= seven_days_ago) |
            (MarketNews.reported_date >= seven_days_ago)
        )
        .order_by(desc(MarketNews.published_at))
        .limit(limit)
        .offset(offset)
    )
    if category:
        stmt = stmt.where(MarketNews.category == category)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/latest", response_model=List[MarketNewsListItem])
async def latest_news(
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest published news from last 7 days."""
    seven_days_ago = dt_date.today() - timedelta(days=7)
    result = await db.execute(
        select(MarketNews)
        .where(MarketNews.status == NewsStatus.PUBLISHED.value)
        .where(
            (MarketNews.published_at >= seven_days_ago) |
            (MarketNews.reported_date >= seven_days_ago)
        )
        .order_by(desc(MarketNews.published_at))
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/search/query", response_model=List[MarketNewsListItem])
async def search_news(
    q: str = Query(..., min_length=2),
    category: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search published news."""
    from sqlalchemy import or_
    stmt = (
        select(MarketNews)
        .where(MarketNews.status == NewsStatus.PUBLISHED.value)
        .where(
            or_(
                MarketNews.title.ilike(f"%{q}%"),
                MarketNews.content.ilike(f"%{q}%"),
                MarketNews.summary.ilike(f"%{q}%"),
                MarketNews.tags.ilike(f"%{q}%"),
            )
        )
        .order_by(desc(MarketNews.published_at))
        .limit(limit)
    )
    if category:
        stmt = stmt.where(MarketNews.category == category)
    result = await db.execute(stmt)
    return result.scalars().all()


# ── Admin endpoints ───────────────────────────────────────────────

@router.get("/admin/all", response_model=List[MarketNewsListItem])
async def admin_list_all(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """List all news articles for moderation (admin only)."""
    stmt = select(MarketNews).order_by(desc(MarketNews.created_at)).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(MarketNews.status == status)
    result = await db.execute(stmt)
    return result.scalars().all()


def _create_article_from_ai_data(data: dict, target_status: str) -> MarketNews:
    """Create a MarketNews record from AI-generated data."""
    reported_date = None
    if data.get("reported_date"):
        reported_str = data["reported_date"]
        try:
            if isinstance(reported_str, str):
                reported_date = dt_date.fromisoformat(reported_str)
            elif isinstance(reported_str, dt_date):
                reported_date = reported_str
        except (ValueError, TypeError):
            reported_date = dt_date.today()

    return MarketNews(
        title=data["title"],
        content=data["content"],
        summary=data.get("summary", ""),
        source=data.get("source", "AI Generated"),
        source_url=data.get("source_url"),
        category=data.get("category", "market"),
        status=target_status,
        ai_model=ANTHROPIC_MODEL,
        tags=data.get("tags", ""),
        image_url=data.get("image_url"),
        reported_date=reported_date,
    )


async def _bg_generate_articles(
    count: int, topic, period_days, language, categories, auto_publish: bool,
):
    """
    Background task: generate articles ONE AT A TIME and write to DB directly.
    Uses its own DB session so it can outlive the request.
    """
    from app.database import AsyncSessionLocal
    from app.models.market_news import MarketNews

    target_status = NewsStatus.PUBLISHED.value if auto_publish else NewsStatus.PENDING_REVIEW.value
    generated = 0

    for i in range(count):
        try:
            single_data = await generate_news_articles(
                topic=topic,
                count=1,
                period_days=period_days,
                language=language,
                categories=categories,
            )
        except Exception as e:
            logger.error(f"Background generation failed for article {i+1}/{count}: {e}")
            continue

        if not single_data:
            continue

        # Save to DB immediately so we don't lose progress
        try:
            async with AsyncSessionLocal() as db:
                for data in single_data:
                    article = _create_article_from_ai_data(data, target_status)
                    db.add(article)
                await db.commit()
                generated += len(single_data)
                logger.info(f"Background: {generated}/{count} articles saved")
        except Exception as e:
            logger.error(f"Failed to save article {i+1}: {e}")

    logger.info(f"Background generation complete: {generated}/{count} articles")


@router.post("/admin/generate")
async def admin_generate_news(
    req: NewsGenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Generate news articles using AI. Runs in background.
    Responds immediately — articles appear within 2-3 minutes.
    """
    # Start background generation
    background_tasks.add_task(
        _bg_generate_articles,
        count=req.count,
        topic=req.topic,
        period_days=req.period_days,
        language=req.language,
        categories=req.categories,
        auto_publish=req.auto_publish,
    )

    return {
        "generating": True,
        "count": req.count,
        "topic": req.topic or "all",
        "status": "A gerar em background. Atualiza a pagina dentro de 1-2 minutos.",
        "auto_publish": req.auto_publish,
    }


@router.post("/{news_id}/publish", response_model=MarketNewsRead)
async def admin_publish(
    news_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Publish a news article (admin only)."""
    result = await db.execute(select(MarketNews).where(MarketNews.id == news_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    article.status = NewsStatus.PUBLISHED.value
    article.published_at = datetime.now(timezone.utc)
    article.reviewed_by = current_user.id
    await db.commit()
    return article


@router.post("/{news_id}/reject", response_model=MarketNewsRead)
async def admin_reject(
    news_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Reject a news article (admin only)."""
    result = await db.execute(select(MarketNews).where(MarketNews.id == news_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    article.status = NewsStatus.REJECTED.value
    article.reviewed_by = current_user.id
    await db.commit()
    return article


@router.delete("/{news_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete(
    news_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Delete a news article (admin only)."""
    result = await db.execute(select(MarketNews).where(MarketNews.id == news_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await db.delete(article)
    await db.commit()


@router.get("/admin/diag")
async def admin_diag_anthropic(
    _: User = Depends(require_admin),
):
    """Test Anthropic API connectivity."""
    import os
    from app.config import settings

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    key_source = "env var"
    if not key:
        key = getattr(settings, "anthropic_api_key", "")
        key_source = "settings"
    if not key:
        secret_path = "/etc/secrets/anthropic_api_key"
        if os.path.exists(secret_path):
            with open(secret_path, "r") as f:
                key = f.read().strip()
            key_source = "secret file"

    masked = ""
    if key:
        masked = key[:10] + "..." + key[-4:] if len(key) > 15 else "***"

    result = {
        "key_configured": bool(key),
        "key_source": key_source,
        "key_masked": masked,
        "model": ANTHROPIC_MODEL,
        "api_test": "skipped",
    }

    if key:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "Hello"}],
                    },
                )
            if resp.status_code == 200:
                result["api_test"] = "OK - API responded 200"
            elif resp.status_code == 401:
                result["api_test"] = "FAIL - 401 Unauthorized. Chave invalida."
            elif resp.status_code == 429:
                result["api_test"] = "FAIL - 429 Rate limited."
            else:
                result["api_test"] = f"FAIL - HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            result["api_test"] = f"FAIL - {str(e)[:200]}"

    return result


@router.get("/admin/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Get news statistics for admin dashboard."""
    total = await db.execute(select(func.count()).select_from(MarketNews))
    published = await db.execute(
        select(func.count()).select_from(MarketNews)
        .where(MarketNews.status == NewsStatus.PUBLISHED.value)
    )
    pending = await db.execute(
        select(func.count()).select_from(MarketNews)
        .where(MarketNews.status == NewsStatus.PENDING_REVIEW.value)
    )
    draft = await db.execute(
        select(func.count()).select_from(MarketNews)
        .where(MarketNews.status == NewsStatus.DRAFT.value)
    )
    return {
        "total": total.scalar(),
        "published": published.scalar(),
        "pending_review": pending.scalar(),
        "draft": draft.scalar(),
        "rejected": 0,
    }
