"""
StockSense REST API
-------------------
Exposes processed SEC filing data and FinBERT sentiment scores.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from src.pipeline.db import get_session, wait_for_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Wait for DB on startup before accepting traffic."""
    logger.info("Waiting for database...")
    await asyncio.get_event_loop().run_in_executor(None, wait_for_db)
    logger.info("Database ready — API starting up")
    yield
    logger.info("API shutting down")


app = FastAPI(
    title="StockSense API",
    description="SEC filing sentiment analysis powered by FinBERT",
    version="2.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Scoring state — tracks in-progress background jobs
# ---------------------------------------------------------------------------

_scoring_in_progress = False


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
    sentiment_label: str | None = None
    sentiment_positive: float | None = None
    sentiment_negative: float | None = None
    sentiment_neutral: float | None = None


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


class ScoringResponse(BaseModel):
    status: str
    message: str


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
        raise HTTPException(status_code=503, detail=f"DB unavailable: {exc}") from exc


def _run_scoring(batch_size: int) -> None:
    """
    Background task: run FinBERT scoring on unscored filings.
    Runs in a thread pool so it doesn't block the event loop.
    """
    global _scoring_in_progress
    try:
        from src.sentiment.finbert import MODEL_NAME, score_filing

        with get_session() as session:
            rows = session.execute(
                text("""
                    SELECT f.id, f.raw_text FROM filings f
                    LEFT JOIN sentiment_scores s
                        ON s.filing_id = f.id AND s.model = :model
                    WHERE s.id IS NULL
                      AND f.raw_text IS NOT NULL
                      AND length(f.raw_text) > 100
                    ORDER BY f.filed_at DESC
                    LIMIT :limit
                """),
                {"model": MODEL_NAME, "limit": batch_size},
            ).fetchall()

        logger.info("Scoring %d unscored filings", len(rows))
        scored, failed = 0, 0

        for filing_id, raw_text in rows:
            try:
                result = score_filing(filing_id, raw_text)
                with get_session() as session:
                    session.execute(
                        text("""
                            INSERT INTO sentiment_scores
                                (filing_id, positive, negative, neutral, label, model)
                            VALUES
                                (:filing_id, :positive, :negative, :neutral, :label, :model)
                            ON CONFLICT (filing_id, model) DO NOTHING
                        """),
                        {
                            "filing_id": filing_id,
                            "positive": result.positive,
                            "negative": result.negative,
                            "neutral": result.neutral,
                            "label": result.label,
                            "model": result.model,
                        },
                    )
                scored += 1
            except Exception as exc:
                logger.error("Failed to score filing_id=%d: %s", filing_id, exc)
                failed += 1

        logger.info("Scoring complete: scored=%d failed=%d", scored, failed)
    finally:
        _scoring_in_progress = False


@app.post("/score/trigger", response_model=ScoringResponse, tags=["sentiment"])
async def trigger_scoring(
    background_tasks: BackgroundTasks,
    batch_size: int = Query(50, ge=1, le=200),
):
    """
    Trigger FinBERT sentiment scoring on unscored filings.

    Returns immediately with 202 Accepted and runs scoring as a background task.
    Only one scoring job runs at a time — subsequent requests return 409 if busy.
    """
    global _scoring_in_progress

    if _scoring_in_progress:
        raise HTTPException(
            status_code=409,
            detail="Scoring already in progress. Try again later.",
        )

    _scoring_in_progress = True
    background_tasks.add_task(_run_scoring, batch_size)

    return ScoringResponse(
        status="accepted",
        message=f"Scoring started for up to {batch_size} filings.",
    )


@app.get("/score/status", tags=["sentiment"])
def scoring_status():
    """Check whether a scoring job is currently running."""
    return {"scoring_in_progress": _scoring_in_progress}


@app.get("/filings", response_model=list[FilingSummary], tags=["filings"])
def list_filings(
    ticker: str | None = Query(None, description="Filter by ticker symbol"),
    form_type: str | None = Query(None, description="Filter by form type (10-K, 10-Q, 8-K)"),
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
