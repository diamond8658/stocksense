"""
FinBERT sentiment scoring for SEC filings.

Uses ProsusAI/finbert — a BERT model fine-tuned on financial text.
Processes filings in chunks to handle the 512-token BERT limit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import torch
from transformers import AutoTokenizer, pipeline

logger = logging.getLogger(__name__)

MODEL_NAME = "ProsusAI/finbert"
MAX_CHUNK_TOKENS = 512
CHUNK_OVERLAP = 50  # token overlap between chunks to preserve context


@dataclass
class SentimentResult:
    positive: float
    negative: float
    neutral: float
    label: str  # dominant label
    model: str = MODEL_NAME


def _load_pipeline():
    """Load FinBERT pipeline, using GPU if available."""
    device = 0 if torch.cuda.is_available() else -1
    logger.info("Loading FinBERT on %s", "GPU" if device == 0 else "CPU")
    return pipeline(
        "text-classification",
        model=MODEL_NAME,
        tokenizer=MODEL_NAME,
        device=device,
        top_k=None,  # return all labels with scores
        truncation=True,
        max_length=MAX_CHUNK_TOKENS,
    )


# Module-level cache — load once per process
_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = _load_pipeline()
    return _pipeline


def _chunk_text(text: str, tokenizer, chunk_size: int = MAX_CHUNK_TOKENS) -> list[str]:
    """
    Split text into overlapping chunks that fit within BERT's token limit.
    Returns decoded string chunks rather than raw token IDs.
    """
    tokens = tokenizer.encode(text, add_special_tokens=False)
    stride = chunk_size - CHUNK_OVERLAP
    chunks = []
    for start in range(0, len(tokens), stride):
        chunk_tokens = tokens[start : start + chunk_size]
        chunk_text = tokenizer.decode(chunk_tokens, skip_special_tokens=True)
        chunks.append(chunk_text)
        if start + chunk_size >= len(tokens):
            break
    return chunks or [text[:2000]]  # fallback for very short texts


def score_text(text: str) -> SentimentResult:
    """
    Score a block of financial text using FinBERT.

    For texts longer than 512 tokens, splits into overlapping chunks,
    scores each, and averages the probabilities.

    Args:
        text: Raw filing text to score.

    Returns:
        SentimentResult with averaged positive/negative/neutral scores.
    """
    if not text or not text.strip():
        return SentimentResult(positive=0.0, negative=0.0, neutral=1.0, label="neutral")

    nlp = get_pipeline()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    chunks = _chunk_text(text, tokenizer)
    logger.debug("Scoring %d chunks for text of length %d", len(chunks), len(text))

    pos_scores, neg_scores, neu_scores = [], [], []

    for chunk in chunks:
        try:
            results: list[dict[str, Any]] = nlp(chunk)[0]  # type: ignore[index]
            scores = {r["label"].lower(): r["score"] for r in results}
            pos_scores.append(scores.get("positive", 0.0))
            neg_scores.append(scores.get("negative", 0.0))
            neu_scores.append(scores.get("neutral", 0.0))
        except Exception as exc:
            logger.warning("Chunk scoring failed: %s", exc)
            continue

    if not pos_scores:
        return SentimentResult(positive=0.0, negative=0.0, neutral=1.0, label="neutral")

    positive = sum(pos_scores) / len(pos_scores)
    negative = sum(neg_scores) / len(neg_scores)
    neutral = sum(neu_scores) / len(neu_scores)

    # Dominant label
    label = max(
        [("positive", positive), ("negative", negative), ("neutral", neutral)],
        key=lambda x: x[1],
    )[0]

    return SentimentResult(
        positive=round(positive, 4),
        negative=round(negative, 4),
        neutral=round(neutral, 4),
        label=label,
    )


def score_filing(filing_id: int, raw_text: str) -> SentimentResult:
    """
    Convenience wrapper that logs filing context around scoring.

    Args:
        filing_id: Database ID of the filing (for logging).
        raw_text: Extracted text of the filing.

    Returns:
        SentimentResult.
    """
    logger.info("Scoring filing_id=%d (%d chars)", filing_id, len(raw_text))
    result = score_text(raw_text)
    logger.info(
        "filing_id=%d → %s (pos=%.3f neg=%.3f neu=%.3f)",
        filing_id,
        result.label,
        result.positive,
        result.negative,
        result.neutral,
    )
    return result
