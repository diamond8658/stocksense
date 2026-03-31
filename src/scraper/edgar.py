"""
SEC Edgar scraper for StockSense.

Fetches filings from the SEC EDGAR submissions API.
Rotates User-Agent headers and respects SEC rate limits (10 req/sec max).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# SEC requires a descriptive User-Agent identifying the requester
_USER_AGENTS = [
    "StockSense/2.0 (research project; contact: jcheng20006@gmail.com)",
    "StockSense-Pipeline/2.0 (portfolio; contact: jcheng20006@gmail.com)",
]

SEC_BASE = "https://data.sec.gov"
_REQUEST_DELAY = 0.12  # stay well under 10 req/sec SEC limit


@dataclass
class FilingRecord:
    ticker: str
    cik: str
    form_type: str
    filed_at: date
    period_of_report: date | None
    accession_number: str
    company_name: str
    filing_url: str
    raw_text: str


def _make_session(ua_index: int = 0) -> requests.Session:
    """Build a requests session with retry logic and SEC-compliant headers."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _USER_AGENTS[ua_index % len(_USER_AGENTS)],
            "Accept-Encoding": "gzip, deflate",
        }
    )
    retry = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _get_cik(ticker: str, session: requests.Session) -> str:
    """Resolve a stock ticker to its SEC CIK number."""
    tickers_url = "https://www.sec.gov/files/company_tickers.json"
    time.sleep(_REQUEST_DELAY)
    # Use a plain request without any Host header override
    resp = requests.get(
        tickers_url,
        headers={"User-Agent": _USER_AGENTS[0]},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"CIK not found for ticker: {ticker}")


def _get_filing_urls(
    cik: str,
    form_type: str,
    session: requests.Session,
    limit: int = 10,
) -> list[dict]:
    """Fetch recent filing metadata for a CIK from the EDGAR submissions API."""
    url = f"{SEC_BASE}/submissions/CIK{cik}.json"
    time.sleep(_REQUEST_DELAY)
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filed_dates = recent.get("filingDate", [])
    periods = recent.get("reportDate", [])
    company_name = data.get("name", "")

    # Strip leading zeros from CIK for use in archive URLs
    cik_int = int(cik)

    results = []
    for form, acc, filed, period in zip(forms, accessions, filed_dates, periods, strict=False):
        if form == form_type:
            acc_clean = acc.replace("-", "")
            # Correct EDGAR archive URL: uses integer CIK (no leading zeros)
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{acc}.txt"
            results.append(
                {
                    "form_type": form,
                    "accession_number": acc,
                    "filed_at": filed,
                    "period_of_report": period or None,
                    "company_name": company_name,
                    "filing_url": filing_url,
                }
            )
            if len(results) >= limit:
                break

    return results


def _extract_text(filing_url: str, session: requests.Session) -> str:
    """
    Download a filing's full submission text file and extract readable content.
    The .txt file at the EDGAR archive URL is the complete submission package.
    Strips SGML/HTML tags and trims to first 50k chars for FinBERT input.
    """
    time.sleep(_REQUEST_DELAY)
    try:
        resp = requests.get(
            filing_url,
            headers={"User-Agent": _USER_AGENTS[0]},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.text
        # Strip SGML and HTML tags
        clean = re.sub(r"<[^>]+>", " ", raw)
        # Collapse whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:50_000]
    except Exception as exc:
        logger.warning("Failed to fetch filing text from %s: %s", filing_url, exc)
        return ""


def scrape_filings(
    tickers: list[str],
    form_type: str = "10-K",
    limit_per_ticker: int = 5,
) -> Iterator[FilingRecord]:
    """
    Scrape SEC EDGAR for filings for a list of tickers.

    Args:
        tickers: List of stock ticker symbols.
        form_type: SEC form type to fetch (10-K, 10-Q, 8-K).
        limit_per_ticker: Max number of filings to fetch per ticker.

    Yields:
        FilingRecord instances for each filing found.
    """
    session = _make_session()

    for i, ticker in enumerate(tickers):
        # Rotate User-Agent every 50 requests to reduce fingerprinting
        if i % 50 == 0 and i > 0:
            session = _make_session(ua_index=i // 50)

        try:
            logger.info("Fetching CIK for %s", ticker)
            cik = _get_cik(ticker, session)

            logger.info("Fetching %s filings for %s (CIK %s)", form_type, ticker, cik)
            filings_meta = _get_filing_urls(cik, form_type, session, limit=limit_per_ticker)

            for meta in filings_meta:
                logger.info("Extracting text from %s", meta["filing_url"])
                raw_text = _extract_text(meta["filing_url"], session)

                yield FilingRecord(
                    ticker=ticker.upper(),
                    cik=cik,
                    form_type=meta["form_type"],
                    filed_at=date.fromisoformat(meta["filed_at"]),
                    period_of_report=(
                        date.fromisoformat(meta["period_of_report"])
                        if meta["period_of_report"]
                        else None
                    ),
                    accession_number=meta["accession_number"],
                    company_name=meta["company_name"],
                    filing_url=meta["filing_url"],
                    raw_text=raw_text,
                )

        except Exception as exc:
            logger.error("Failed to scrape %s: %s", ticker, exc)
            continue
