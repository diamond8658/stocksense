import time
from datetime import datetime, timedelta
from typing import Any

import finnhub
import pandas as pd
import spacy
from spacy.language import Language
from textblob import TextBlob


class StockSourcer:
    def __init__(self, api_key: str):
        """Initializes API clients and the NLP model."""
        if not api_key:
            raise ValueError("Finnhub API Key is required.")

        self.finnhub_client = finnhub.Client(api_key=api_key)

        # Load spaCy model for granular entity extraction
        self.nlp: Language | None = None
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            print("⚠️ spaCy model not found. Run: python -m spacy download en_core_web_sm")

    def _get_sentiment(self, text: str) -> float:
        """Calculates polarity: -1.0 (Negative) to 1.0 (Positive)."""
        if not text or pd.isna(text):
            return 0.0

        blob = TextBlob(str(text))
        # Cast to Any to prevent Pylance 'cached_property' errors
        sentiment: Any = blob.sentiment
        return float(sentiment[0])

    def _extract_entities(self, text: str) -> dict:
        """Granular Analysis: Extracts Orgs, Money, and Percentages."""
        if not self.nlp or not text:
            return {"orgs": [], "money": [], "percent": []}

        doc = self.nlp(text)
        return {
            "orgs": [ent.text for ent in doc.ents if ent.label_ == "ORG"],
            "money": [ent.text for ent in doc.ents if ent.label_ == "MONEY"],
            "percent": [ent.text for ent in doc.ents if ent.label_ == "PERCENT"],
        }

    def get_company_news(self, ticker: str, days_back: int = 7):
        """Fetches news and performs granular NLP analysis."""
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        try:
            raw_news = self.finnhub_client.company_news(ticker, _from=from_date, to=to_date)
        except Exception as e:
            print(f"⚠️ API Error for {ticker}: {e}")
            return pd.DataFrame()

        if not raw_news:
            return pd.DataFrame()

        df = pd.DataFrame(raw_news)
        df["datetime"] = pd.to_datetime(df["datetime"], unit="s")

        # 1. Basic Sentiment
        df["sentiment_score"] = df["headline"].apply(self._get_sentiment)

        # 2. Granular Entities (NER)
        entities_series = df["headline"].apply(self._extract_entities)
        df["mentioned_orgs"] = entities_series.apply(lambda x: x["orgs"])
        df["financial_figures"] = entities_series.apply(lambda x: x["money"] + x["percent"])

        cols = [
            "datetime",
            "headline",
            "sentiment_score",
            "mentioned_orgs",
            "financial_figures",
            "source",
            "url",
        ]
        return df[cols].sort_values(by="datetime", ascending=False)

    def batch_fetch_news(self, tickers: list[str], days_back: int = 3):
        """Loops through tickers with a 1.1s delay for rate-limiting."""
        all_dfs = []
        for ticker in tickers:
            print(f"🔍 Analyzing {ticker}...")
            df = self.get_company_news(ticker, days_back)
            if not df.empty:
                df["ticker"] = ticker
                all_dfs.append(df)
            time.sleep(1.1)

        return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()

    def get_executive_summary(self, df: pd.DataFrame):
        """Generates a text briefing highlighting the most 'extreme' sentiment."""
        if df.empty:
            return "No data."

        summary = ["--- 📰 EXECUTIVE GRANULAR BRIEFING ---"]
        for ticker in df["ticker"].unique():
            ticker_data = df[df["ticker"] == ticker]
            top_story = ticker_data.loc[ticker_data["sentiment_score"].abs().idxmax()]

            label = (
                "🟢 BULL"
                if top_story["sentiment_score"] > 0.1
                else "🔴 BEAR"
                if top_story["sentiment_score"] < -0.1
                else "⚪ NEUT"
            )
            figures = (
                f" | Data found: {top_story['financial_figures']}"
                if top_story["financial_figures"]
                else ""
            )

            summary.append(f"[{ticker}] {label}: {top_story['headline']}{figures}")

        return "\n".join(summary)
