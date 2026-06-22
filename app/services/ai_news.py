"""
AI News Generation Service — uses Anthropic Claude to generate
Angolan market news articles.

Usage:
    from app.services.ai_news import generate_news_articles
    articles = await generate_news_articles(topic="BODIVA", count=3)
"""
import httpx
import json
from datetime import datetime, timezone
from typing import List, Dict, Any

from app.config import settings

# Anthropic API configuration
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def _get_api_key() -> str:
    """Get the Anthropic API key from env var, pydantic settings, or Render secret file."""
    import os
    # 1. Environment variable (set via Render → Environment tab)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    # 2. Pydantic settings (reads from .env)
    key = getattr(settings, "anthropic_api_key", "")
    if key:
        return key
    # 3. Render Secret File at /etc/secrets/anthropic_api_key
    secret_path = "/etc/secrets/anthropic_api_key"
    if os.path.exists(secret_path):
        with open(secret_path, "r") as f:
            key = f.read().strip()
    return key


_NEWS_SYSTEM_PROMPT = """You are a journalist writing about Angola's financial market. Generate 1 news article in valid JSON format.

Use these VERIFIED data points: BNA rate=17.00%, inflation=10.88% (May 2026 INE), USD/AOA=910, oil Brent=$75, IAC=10% (Lei 14/25).

Categories: macro, bodiva, fiscal, corporate, market. Reference: BNA, BODIVA, UGD, OT bonds.

For each article, provide:
- title: compelling headline (max 120 chars)
- content: short article (100-150 words, 3 paragraphs max)
- summary: 1-sentence summary
- category: one of [macro, bodiva, fiscal, corporate, market]
- tags: comma-separated relevant tags (e.g., "BNA,interest-rates,kwanza")
- source: the institution or publication this would be attributed to (e.g., "BNA", "BODIVA", "Jornal de Angola", "Expansao", "Reuters Africa", "Bloomberg Africa")
- source_url: realistic URL for the source website (e.g., "https://www.bna.ao", "https://www.bodiva.ao")
- image_query: 2-3 keywords for a relevant photo (e.g., "angola luanda finance", "central bank money", "stock market trading")
- article_date: the date the news event happened / was reported (YYYY-MM-DD format). This MUST be a date within the last {period_days} days. DO NOT use future dates.

CRITICAL: Use the CURRENT macro data provided above. Do NOT invent or hallucinate rates or dates.
The BNA rate is 17.00% as of June 2026. Inflation is 10.88%. Do not use outdated figures.

IMPORTANT: Return ONLY a valid JSON array. No markdown, no explanation.

Example format:
[
  {
    "title": "BNA maintains key interest rate at 19.5% amid inflation concerns",
    "content": "The Bank of Angola (BNA) decided on Wednesday to maintain the benchmark TBC rate at 19.50%...",
    "summary": "BNA holds rates steady citing inflation concerns. Move expected to stabilize the kwanza.",
    "category": "macro",
    "tags": "BNA,TBC,interest-rates,monetary-policy,kwanza,inflation",
    "source": "BNA",
    "source_url": "https://www.bna.ao",
    "image_query": "angola central bank monetary policy"
  }
]"""


async def generate_news_articles(
    topic: str | None = None,
    count: int = 3,
    period_days: int = 7,
    language: str = "en",
    categories: list | None = None,
) -> List[Dict[str, Any]]:
    """
    Generate news articles using Anthropic Claude API.
    
    Args:
        topic: Optional topic filter ("BODIVA", "BNA", "macro", etc.)
        count: Number of articles to generate (default 3)
    
    Returns:
        List of dicts with title, content, summary, category, tags
    """
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not configured. "
            "Set the ANTHROPIC_API_KEY environment variable in your .env file."
        )

    # Build the user prompt
    user_prompt = f"Generate {count} financial news articles about the Angolan market."
    if topic:
        user_prompt += f' Focus on the topic: "{topic}".'
    if categories:
        user_prompt += f' Only use these categories: {", ".join(categories)}.'
    user_prompt += f" Write in {'Portuguese (European)' if language == 'pt' else 'English'}."
    user_prompt += f" The news should reflect developments from the last {period_days} day(s)."
    user_prompt += " Current date: " + datetime.now(timezone.utc).strftime("%Y-%m-%d")
    user_prompt += "\n\nReturn ONLY valid JSON array."

    system_prompt = _NEWS_SYSTEM_PROMPT.replace("__COUNT__", str(count))
    system_prompt = system_prompt.replace("{period_days}", str(period_days))

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 2048,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ],
            },
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Anthropic API error: {response.status_code} — {response.text}"
            )

        data = response.json()
        content = data.get("content", [])
        if not content:
            raise RuntimeError("Empty response from Anthropic API")
        stop_reason = data.get("stop_reason", "")
        if stop_reason == "max_tokens":
            raise RuntimeError(
                "Resposta truncada pelo Anthropic (max_tokens atingido). "
                "Reduz o número de artigos a gerar."
            )

        # Extract JSON from the response text
        text = content[0].get("text", "")
        # Find JSON array in the response
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end == 0:
            raise RuntimeError("No JSON array found in AI response")

        articles = json.loads(text[start:end])

        # Validate and enrich each article
        required = {"title", "content", "summary", "category", "tags"}
        valid_articles = []
        for a in articles:
            if required.issubset(a.keys()):
                if not a.get("image_url") and a.get("image_query"):
                    a["image_url"] = None  # Skip loremflickr — production ready
                # Extract reported_date from article_date field
                if "article_date" in a and a["article_date"]:
                    a["reported_date"] = a["article_date"]
                elif not a.get("reported_date"):
                    from datetime import date as dt_date
                    a["reported_date"] = dt_date.today().isoformat()
                valid_articles.append(a)

        return valid_articles


async def generate_weekly_newsletter() -> Dict[str, Any]:
    """
    Generate a weekly newsletter summarizing Angolan market developments.
    Returns a dict with title, content, and key highlights.
    """
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    prompt = """Write a weekly newsletter for Angolan investors covering:
1. Key BODIVA market movements (OT bonds, T-bills)
2. BNA monetary policy updates
3. Kwanza exchange rate trends
4. Major corporate news
5. Macro economic indicators
6. Outlook for the coming week

Format as a professional newsletter with sections, bullet points, and data.
Include specific numbers and dates where possible.
Return as JSON: {"title": "...", "content": "...", "highlights": ["...", "..."]}"""

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 4000,
                "messages": [{"role": "user", "content": prompt}],
            },
        )

        if response.status_code != 200:
            raise RuntimeError(f"Anthropic API error: {response.status_code}")

        data = response.json()
        text = data.get("content", [{}])[0].get("text", "")
        
        # Extract JSON
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1:
            return {"title": "Weekly Market Update", "content": text, "highlights": []}
        
        return json.loads(text[start:end])
