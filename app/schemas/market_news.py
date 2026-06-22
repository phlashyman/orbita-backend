"""
Schemas Pydantic para MarketNews.
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class MarketNewsCreate(BaseModel):
    title: str = Field(..., max_length=300)
    content: str
    summary: str | None = None
    source: str = "AI Generated"
    source_url: str | None = None
    author: str | None = None
    category: str | None = None
    tags: str | None = None
    image_url: str | None = None


class MarketNewsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    content: str
    summary: str | None
    source: str
    source_url: str | None
    author: str | None
    category: str | None
    status: str
    published_at: datetime | None
    reviewed_by: UUID | None
    ai_model: str | None
    tags: str | None
    image_url: str | None
    created_at: datetime
    updated_at: datetime


class MarketNewsListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    content: str | None = None
    summary: str | None = None
    source: str
    source_url: str | None = None
    category: str | None = None
    status: str
    published_at: datetime | None = None
    tags: str | None = None
    image_url: str | None = None
    created_at: datetime | None = None


class MarketNewsUpdate(BaseModel):
    title: str | None = Field(None, max_length=300)
    content: str | None = None
    summary: str | None = None
    category: str | None = None
    tags: str | None = None
    status: str | None = None
    image_url: str | None = None


class MarketNewsStatusUpdate(BaseModel):
    status: str  # PUBLISHED, REJECTED, PENDING_REVIEW


class NewsGenerateRequest(BaseModel):
    topic: str | None = None          # "BODIVA", "BNA", "macro", etc.
    count: int = Field(3, ge=1, le=10)
    period_days: int = Field(7, ge=1, le=90)   # how recent the news context should be
    language: str = "en"               # "en" or "pt"
    categories: list[str] | None = None  # ["macro","bodiva",...] — None = all
    auto_publish: bool = False         # skip PENDING_REVIEW, publish directly
    force: bool = False


class NewsGenerateResponse(BaseModel):
    generated: int
    articles: list[MarketNewsListItem]


class NewsSearchRequest(BaseModel):
    query: str | None = None
    category: str | None = None
    status: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class NewsSearchResponse(BaseModel):
    total: int
    results: list[MarketNewsListItem]
