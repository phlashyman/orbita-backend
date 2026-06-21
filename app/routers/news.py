"""
News Router — public news feed + admin moderation + AI generation.
"""
from datetime import datetime, timezone, date as dt_date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
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

router = APIRouter(prefix="/news", tags=["News"])


# ── Public endpoints ──────────────────────────────────────────────

@router.get("/", response_model=List[MarketNewsListItem])
async def list_news(
    category: str | None = Query(None, description="Filter by category: macro, bodiva, fiscal, corporate, market"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List published news articles from the last 7 days (public, no auth required)."""
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
    """Get the latest published news from last 7 days (for landing page, dashboard)."""
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


@router.get("/{news_id}", response_model=MarketNewsRead)
async def get_news(
    news_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single news article by ID (public)."""
    result = await db.execute(
        select(MarketNews).where(
            MarketNews.id == news_id,
            MarketNews.status == NewsStatus.PUBLISHED.value,
        )
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.get("/search/query", response_model=List[MarketNewsListItem])
async def search_news(
    q: str = Query(..., min_length=2, description="Search query"),
    category: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search published news by title/content."""
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


@router.post("/admin/generate", response_model=NewsGenerateResponse)
async def admin_generate_news(
    req: NewsGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Generate news articles using AI (admin only).
    
    Set ANTHROPIC_API_KEY in your .env file first:
        ANTHROPIC_API_KEY=sk-ant-...
    """
    try:
        # Generate articles ONE AT A TIME — each API call is fast (<30s)
        articles_data = []
        for i in range(req.count):
            single_data = await generate_news_articles(
                topic=req.topic,
                count=1,  # ONE article per API call
                period_days=req.period_days,
                language=req.language,
                categories=req.categories,
            )
            articles_data.extend(single_data)
    except RuntimeError as e:
        import traceback
        msg = str(e)
        # Extract the actual API error if present
        if "Anthropic API error:" in msg:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Erro da API Anthropic: {msg.split('Anthropic API error:')[1].strip() if 'Anthropic API error:' in msg else msg}",
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=msg,
        )
    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro inesperado: {str(e)}",
        )

    target_status = NewsStatus.PUBLISHED.value if req.auto_publish else NewsStatus.PENDING_REVIEW.value

    created_articles = []
    for data in articles_data:
        # Parse reported_date from the AI
        reported_date = None
        if data.get("reported_date"):
            from datetime import date as dt_date
            reported_str = data["reported_date"]
            try:
                if isinstance(reported_str, str):
                    reported_date = dt_date.fromisoformat(reported_str)
                elif isinstance(reported_str, dt_date):
                    reported_date = reported_str
            except (ValueError, TypeError):
                reported_date = dt_date.today()

        article = MarketNews(
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
        db.add(article)
        created_articles.append(article)

    await db.flush()

    # Return as list items
    return NewsGenerateResponse(
        generated=len(created_articles),
        articles=[
            MarketNewsListItem.model_validate(a) for a in created_articles
        ],
    )


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
    await db.flush()
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
    await db.flush()
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
    await db.flush()


@router.get("/admin/diag", summary="Testar conexao a API Anthropic")
async def admin_diag_anthropic(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Test Anthropic API connectivity — mostra se a chave esta configurada e se a API responde."""
    import os
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
                result["api_test"] = "FAIL - 401 Unauthorized. A chave API e invalida ou expirou."
            elif resp.status_code == 404:
                result["api_test"] = "FAIL - 404 Model not found. O nome do modelo esta errado."
            elif resp.status_code == 429:
                result["api_test"] = "FAIL - 429 Rate limited. Limite de requisicoes atingido."
            else:
                body = resp.text[:300]
                result["api_test"] = f"FAIL - HTTP {resp.status_code}: {body}"
        except Exception as e:
            result["api_test"] = f"FAIL - Network error: {str(e)[:200]}"

    return result


@router.get("/admin/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Get news statistics for admin dashboard."""
    from sqlalchemy import func

    total = await db.execute(select(func.count()).select_from(MarketNews))
    published = await db.execute(
        select(func.count())
        .select_from(MarketNews)
        .where(MarketNews.status == NewsStatus.PUBLISHED.value)
    )
    pending = await db.execute(
        select(func.count())
        .select_from(MarketNews)
        .where(MarketNews.status == NewsStatus.PENDING_REVIEW.value)
    )
    draft = await db.execute(
        select(func.count())
        .select_from(MarketNews)
        .where(MarketNews.status == NewsStatus.DRAFT.value)
    )
    rejected = await db.execute(
        select(func.count())
        .select_from(MarketNews)
        .where(MarketNews.status == NewsStatus.REJECTED.value)
    )

    return {
        "total": total.scalar(),
        "published": published.scalar(),
        "pending_review": pending.scalar(),
        "draft": draft.scalar(),
        "rejected": rejected.scalar(),
    }
