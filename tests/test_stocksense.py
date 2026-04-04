"""
Unit tests for StockSense scraper and sentiment modules.
DB-dependent tests use a real PostgreSQL instance (provided by CI).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.scraper.edgar import FilingRecord, scrape_filings
from src.sentiment.finbert import SentimentResult, score_text

# ---------------------------------------------------------------------------
# Scraper tests
# ---------------------------------------------------------------------------


class TestEdgarScraper:
    def test_filing_record_dataclass(self):
        record = FilingRecord(
            ticker="AAPL",
            cik="0000320193",
            form_type="10-K",
            filed_at=date(2024, 11, 1),
            period_of_report=date(2024, 9, 28),
            accession_number="0000320193-24-000123",
            company_name="Apple Inc.",
            filing_url="https://www.sec.gov/...",
            raw_text="Apple reported record revenue...",
        )
        assert record.ticker == "AAPL"
        assert record.form_type == "10-K"

    @patch("src.scraper.edgar._get_cik", return_value="0000320193")
    @patch("src.scraper.edgar._get_filing_urls")
    @patch("src.scraper.edgar._extract_text", return_value="Sample filing text")
    def test_scrape_filings_yields_records(self, mock_text, mock_urls, mock_cik):
        mock_urls.return_value = [
            {
                "form_type": "10-K",
                "accession_number": "0000320193-24-000001",
                "filed_at": "2024-11-01",
                "period_of_report": "2024-09-28",
                "company_name": "Apple Inc.",
                "filing_url": "https://www.sec.gov/test",
            }
        ]

        records = list(scrape_filings(["AAPL"], form_type="10-K", limit_per_ticker=1))
        assert len(records) == 1
        assert records[0].ticker == "AAPL"
        assert records[0].raw_text == "Sample filing text"

    @patch("src.scraper.edgar._get_cik", side_effect=ValueError("CIK not found"))
    def test_scrape_filings_skips_on_error(self, mock_cik):
        """Errors on individual tickers should not crash the whole scrape."""
        records = list(scrape_filings(["INVALID"], form_type="10-K"))
        assert records == []


# ---------------------------------------------------------------------------
# Sentiment tests
# ---------------------------------------------------------------------------


class TestFinBERT:
    def test_score_empty_text_returns_neutral(self):
        result = score_text("")
        assert result.label == "neutral"
        assert result.neutral == 1.0

    def test_score_whitespace_only_returns_neutral(self):
        result = score_text("   \n\t  ")
        assert result.label == "neutral"

    @patch("src.sentiment.finbert.get_pipeline")
    def test_score_positive_text(self, mock_pipeline):
        mock_pipeline.return_value = lambda text, **kwargs: [
            [
                {"label": "positive", "score": 0.85},
                {"label": "negative", "score": 0.05},
                {"label": "neutral", "score": 0.10},
            ]
        ]
        result = score_text("Record revenue and exceptional growth exceeded all expectations.")
        assert result.label == "positive"
        assert result.positive > result.negative
        assert result.positive > result.neutral

    @patch("src.sentiment.finbert.get_pipeline")
    def test_score_negative_text(self, mock_pipeline):
        mock_pipeline.return_value = lambda text, **kwargs: [
            [
                {"label": "positive", "score": 0.05},
                {"label": "negative", "score": 0.88},
                {"label": "neutral", "score": 0.07},
            ]
        ]
        result = score_text("Significant losses and declining revenue raised concerns.")
        assert result.label == "negative"
        assert result.negative > result.positive

    @patch("src.sentiment.finbert.get_pipeline")
    def test_scores_sum_to_approximately_one(self, mock_pipeline):
        mock_pipeline.return_value = lambda text, **kwargs: [
            [
                {"label": "positive", "score": 0.33},
                {"label": "negative", "score": 0.33},
                {"label": "neutral", "score": 0.34},
            ]
        ]
        result = score_text("Revenue was in line with expectations.")
        total = result.positive + result.negative + result.neutral
        assert abs(total - 1.0) < 0.01

    def test_sentiment_result_dataclass(self):
        result = SentimentResult(positive=0.7, negative=0.1, neutral=0.2, label="positive")
        assert result.model == "ProsusAI/finbert"
        assert result.label == "positive"


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestAPI:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from src.api.main import app

        return TestClient(app)

    @patch("src.api.main.get_session")
    def test_health_endpoint(self, mock_session, client):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_session.return_value = mock_ctx

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @patch("src.api.main.get_session")
    def test_list_filings_empty(self, mock_session, client):
        mock_session_obj = MagicMock()
        mock_session_obj.execute.return_value.fetchall.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session_obj)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_session.return_value = mock_ctx

        response = client.get("/filings")
        assert response.status_code == 200
        assert response.json() == []

    @patch("src.api.main.get_session")
    def test_list_filings_ticker_filter(self, mock_session, client):
        mock_session_obj = MagicMock()
        mock_session_obj.execute.return_value.fetchall.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session_obj)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_session.return_value = mock_ctx

        response = client.get("/filings?ticker=AAPL")
        assert response.status_code == 200

    def test_list_filings_invalid_limit(self, client):
        response = client.get("/filings?limit=0")
        assert response.status_code == 422  # validation error

    @patch("src.api.main.get_session")
    def test_get_filing_not_found(self, mock_session, client):
        mock_session_obj = MagicMock()
        mock_session_obj.execute.return_value.fetchone.return_value = None
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_session_obj)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_session.return_value = mock_ctx

        response = client.get("/filings/99999")
        assert response.status_code == 404
