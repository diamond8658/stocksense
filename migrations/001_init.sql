-- StockSense schema
-- Run once against the target PostgreSQL instance

CREATE TABLE IF NOT EXISTS filings (
    id              SERIAL PRIMARY KEY,
    ticker          VARCHAR(10)  NOT NULL,
    cik             VARCHAR(10)  NOT NULL,
    form_type       VARCHAR(20)  NOT NULL,   -- e.g. 10-K, 10-Q, 8-K
    filed_at        DATE         NOT NULL,
    period_of_report DATE,
    accession_number VARCHAR(25) NOT NULL UNIQUE,
    company_name    TEXT,
    raw_text        TEXT,                    -- extracted body text of the filing
    filing_url      TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_filings_ticker   ON filings (ticker);
CREATE INDEX IF NOT EXISTS idx_filings_filed_at ON filings (filed_at DESC);
CREATE INDEX IF NOT EXISTS idx_filings_form_type ON filings (form_type);

CREATE TABLE IF NOT EXISTS sentiment_scores (
    id          SERIAL PRIMARY KEY,
    filing_id   INTEGER      NOT NULL REFERENCES filings (id) ON DELETE CASCADE,
    positive    FLOAT        NOT NULL,
    negative    FLOAT        NOT NULL,
    neutral     FLOAT        NOT NULL,
    label       VARCHAR(10)  NOT NULL,   -- 'positive' | 'negative' | 'neutral'
    model       VARCHAR(50)  NOT NULL DEFAULT 'ProsusAI/finbert',
    scored_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (filing_id, model)
);

CREATE INDEX IF NOT EXISTS idx_sentiment_filing_id ON sentiment_scores (filing_id);
CREATE INDEX IF NOT EXISTS idx_sentiment_label      ON sentiment_scores (label);
