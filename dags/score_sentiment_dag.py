"""
score_sentiment_dag.py
----------------------
Airflow DAG that picks up unscored filings from PostgreSQL,
runs FinBERT sentiment analysis, and writes scores back.

Schedule: Daily at 08:00 UTC (after ingest_filings completes).
Triggered after ingest_filings_dag via ExternalTaskSensor.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor

logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # filings to score per run (FinBERT is CPU-heavy)

default_args = {
    "owner": "stocksense",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}


def _score_unscored_filings(**context) -> None:
    import requests

    resp = requests.post(
        "http://api:8000/score/trigger",
        params={"batch_size": 50},
        timeout=3600,
    )
    resp.raise_for_status()
    result = resp.json()
    logger.info("Scoring complete: %s", result)


with DAG(
    dag_id="score_sentiment",
    default_args=default_args,
    description="Run FinBERT sentiment scoring on unscored SEC filings",
    schedule_interval="0 8 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["stocksense", "sentiment"],
) as dag:
    wait_for_ingest = ExternalTaskSensor(
        task_id="wait_for_ingest",
        external_dag_id="ingest_filings",
        external_task_id=None,  # wait for the entire DAG
        allowed_states=["success"],
        timeout=3600,
        poke_interval=60,
        mode="reschedule",
    )

    score_task = PythonOperator(
        task_id="score_unscored_filings",
        python_callable=_score_unscored_filings,
    )

    wait_for_ingest >> score_task
