"""
ingest_filings_dag.py
---------------------
Airflow DAG that scrapes SEC EDGAR for new filings and writes them to PostgreSQL.

Schedule: Daily at 06:00 UTC (after SEC EDGAR typically updates overnight).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

# Tickers to track — extend this list as needed
WATCH_LIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",
    "NVDA", "JPM", "GS", "BAC", "WFC",
]

FORM_TYPES = ["10-K", "10-Q", "8-K"]
LIMIT_PER_TICKER = 3  # fetch last N filings per ticker per run

default_args = {
    "owner": "stocksense",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def _ingest_filings(form_type: str, **context) -> None:
    """
    Task function: scrape EDGAR for `form_type` filings and upsert to DB.
    Skips filings already present (idempotent via accession_number UNIQUE).
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from src.scraper.edgar import scrape_filings
    from src.pipeline.db import get_session
    from sqlalchemy import text

    inserted = 0
    skipped = 0

    with get_session() as session:
        for record in scrape_filings(
            tickers=WATCH_LIST,
            form_type=form_type,
            limit_per_ticker=LIMIT_PER_TICKER,
        ):
            try:
                session.execute(
                    text("""
                        INSERT INTO filings
                            (ticker, cik, form_type, filed_at, period_of_report,
                             accession_number, company_name, raw_text, filing_url)
                        VALUES
                            (:ticker, :cik, :form_type, :filed_at, :period_of_report,
                             :accession_number, :company_name, :raw_text, :filing_url)
                        ON CONFLICT (accession_number) DO NOTHING
                    """),
                    {
                        "ticker": record.ticker,
                        "cik": record.cik,
                        "form_type": record.form_type,
                        "filed_at": record.filed_at,
                        "period_of_report": record.period_of_report,
                        "accession_number": record.accession_number,
                        "company_name": record.company_name,
                        "raw_text": record.raw_text,
                        "filing_url": record.filing_url,
                    },
                )
                inserted += 1
            except Exception as exc:
                logger.warning("Failed to insert %s: %s", record.accession_number, exc)
                skipped += 1

    logger.info(
        "form_type=%s: inserted=%d skipped=%d", form_type, inserted, skipped
    )


with DAG(
    dag_id="ingest_filings",
    default_args=default_args,
    description="Scrape SEC EDGAR and ingest filings into PostgreSQL",
    schedule_interval="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["stocksense", "ingest"],
) as dag:

    for form in FORM_TYPES:
        PythonOperator(
            task_id=f"ingest_{form.replace('-', '_').lower()}",
            python_callable=_ingest_filings,
            op_kwargs={"form_type": form},
        )
