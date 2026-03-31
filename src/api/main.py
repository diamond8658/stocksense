"""
StockSense REST API
-------------------
Exposes processed SEC filing data and FinBERT sentiment scores.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from src.pipeline.db import get_session

app = FastAPI(
    title="StockSense API",
    description="SEC filing sentiment analysis powered by FinBERT",
    version="2.0.0",
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class FilingSummary(BaseModel):
    id: int
    ticker: str
    form_type: str
    filed_at: date
    company_name: str
    filing_url: str
    sentiment_label: Optional[str] = None
    sentiment_positive: Optional[float] = None
    sentiment_negative: Optional[float] = None
    sentiment_neutral: Optional[float] = None


class SentimentTrend(BaseModel):
    ticker: str
    filed_at: date
    form_type: str
    label: str
    positive: float
    negative: float
    neutral: float


class HealthResponse(BaseModel):
    status: str
    db: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health():
    """Liveness check — verifies DB connectivity."""
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {exc}")


@app.get("/filings", response_model=list[FilingSummary], tags=["filings"])
def list_filings(
    ticker: Optional[str] = Query(None, description="Filter by ticker symbol"),
    form_type: Optional[str] = Query(None, description="Filter by form type (10-K, 10-Q, 8-K)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List SEC filings with their sentiment scores.
    Results are sorted by filing date descending.
    """
    with get_session() as session:
        query = """
            SELECT
                f.id,
                f.ticker,
                f.form_type,
                f.filed_at,
                f.company_name,
                f.filing_url,
                s.label      AS sentiment_label,
                s.positive   AS sentiment_positive,
                s.negative   AS sentiment_negative,
                s.neutral    AS sentiment_neutral
            FROM filings f
            LEFT JOIN sentiment_scores s ON s.filing_id = f.id
            WHERE 1=1
        """
        params: dict = {"limit": limit, "offset": offset}

        if ticker:
            query += " AND f.ticker = :ticker"
            params["ticker"] = ticker.upper()
        if form_type:
            query += " AND f.form_type = :form_type"
            params["form_type"] = form_type.upper()

        query += " ORDER BY f.filed_at DESC LIMIT :limit OFFSET :offset"

        rows = session.execute(text(query), params).fetchall()

    return [dict(row._mapping) for row in rows]


@app.get("/filings/{filing_id}", response_model=FilingSummary, tags=["filings"])
def get_filing(filing_id: int):
    """Get a single filing by ID including its sentiment score."""
    with get_session() as session:
        row = session.execute(
            text("""
                SELECT
                    f.id, f.ticker, f.form_type, f.filed_at,
                    f.company_name, f.filing_url,
                    s.label, s.positive, s.negative, s.neutral
                FROM filings f
                LEFT JOIN sentiment_scores s ON s.filing_id = f.id
                WHERE f.id = :id
            """),
            {"id": filing_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Filing not found")

    return dict(row._mapping)


@app.get("/sentiment/trend", response_model=list[SentimentTrend], tags=["sentiment"])
def sentiment_trend(
    ticker: str = Query(..., description="Ticker symbol"),
    form_type: str = Query("10-K", description="Form type to trend"),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Return sentiment scores over time for a ticker.
    Useful for plotting sentiment trend lines across earnings cycles.
    """
    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT
                    f.ticker,
                    f.filed_at,
                    f.form_type,
                    s.label,
                    s.positive,
                    s.negative,
                    s.neutral
                FROM filings f
                JOIN sentiment_scores s ON s.filing_id = f.id
                WHERE f.ticker = :ticker
                  AND f.form_type = :form_type
                ORDER BY f.filed_at DESC
                LIMIT :limit
            """),
            {"ticker": ticker.upper(), "form_type": form_type.upper(), "limit": limit},
        ).fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No scored filings found for {ticker} {form_type}",
        )

    return [dict(row._mapping) for row in rows]


@app.get("/sentiment/summary", tags=["sentiment"])
def sentiment_summary(
    ticker: str = Query(..., description="Ticker symbol"),
):
    """
    Aggregate sentiment breakdown for a ticker across all scored filings.
    Returns average positive/negative/neutral and dominant label distribution.
    """
    with get_session() as session:
        row = session.execute(
            text("""
                SELECT
                    COUNT(*)                        AS total_filings,
                    AVG(s.positive)                 AS avg_positive,
                    AVG(s.negative)                 AS avg_negative,
                    AVG(s.neutral)                  AS avg_neutral,
                    SUM(CASE WHEN s.label = 'positive' THEN 1 ELSE 0 END) AS count_positive,
                    SUM(CASE WHEN s.label = 'negative' THEN 1 ELSE 0 END) AS count_negative,
                    SUM(CASE WHEN s.label = 'neutral'  THEN 1 ELSE 0 END) AS count_neutral
                FROM filings f
                JOIN sentiment_scores s ON s.filing_id = f.id
                WHERE f.ticker = :ticker
            """),
            {"ticker": ticker.upper()},
        ).fetchone()

    if not row or row.total_filings == 0:
        raise HTTPException(
            status_code=404, detail=f"No scored filings found for {ticker}"
        )

    return dict(row._mapping)

@app.post("/score/trigger", tags=["sentiment"])
async def trigger_scoring(batch_size: int = 50):
    """Trigger FinBERT scoring on unscored filings."""
    import asyncio
    from src.sentiment.finbert import score_filing, MODEL_NAME
    from sqlalchemy import text

    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT f.id, f.raw_text FROM filings f
                LEFT JOIN sentiment_scores s ON s.filing_id = f.id AND s.model = :model
                WHERE s.id IS NULL AND f.raw_text IS NOT NULL AND length(f.raw_text) > 100
                ORDER BY f.filed_at DESC LIMIT :limit
            """),
            {"model": MODEL_NAME, "limit": batch_size},
        ).fetchall()

    scored, failed = 0, 0
    for filing_id, raw_text in rows:
        try:
            result = score_filing(filing_id, raw_text)
            with get_session() as session:
                session.execute(
                    text("""
                        INSERT INTO sentiment_scores
                            (filing_id, positive, negative, neutral, label, model)
                        VALUES (:filing_id, :positive, :negative, :neutral, :label, :model)
                        ON CONFLICT (filing_id, model) DO NOTHING
                    """),
                    {"filing_id": filing_id, "positive": result.positive,
                     "negative": result.negative, "neutral": result.neutral,
                     "label": result.label, "model": result.model},
                )
            scored += 1
        except Exception as exc:
            failed += 1
    return {"scored": scored, "failed": failed}