# StockSense 📈

An event-driven SEC filing intelligence pipeline with FinBERT sentiment analysis, deployed on Azure.

## Architecture

```
SEC Edgar (source)
      ↓
Airflow DAG  ──── ingest_filings  ──── scrapes + normalizes → PostgreSQL
                  score_sentiment ──── FinBERT inference    → PostgreSQL
      ↓
FastAPI (REST API exposing filings + sentiment scores)
      ↓
Docker Compose (local dev) / Azure Container Apps (production)
      ↓
GitHub Actions (CI: test + lint → CD: build + push → deploy)
```

## Features

- **SEC Edgar scraper** — multi-threaded ingestion of 10-K, 10-Q, and 8-K filings with rotating User-Agent headers and retry logic; processes **500+ reports/hr**
- **FinBERT sentiment scoring** — ProsusAI/finbert fine-tuned on financial text; handles filings longer than BERT's 512-token limit via overlapping chunk averaging
- **Airflow orchestration** — two DAGs with dependency management via `ExternalTaskSensor`; idempotent upserts protect against duplicate runs
- **FastAPI REST API** — endpoints for filing search, sentiment trend, and aggregate summary; Pydantic v2 validation throughout
- **CI/CD via GitHub Actions** — automated lint (ruff), type check (mypy), and pytest on every push; Docker image built and pushed to Azure Container Registry on merge to `main`; deployed to Azure Container Apps

## Quick Start (local)

```bash
# 1. Clone and configure
cp .env.example .env
# Add your Finnhub API key to .env

# 2. Start all services
docker compose up -d

# 3. Run migrations (handled automatically by docker-compose on first run)

# 4. Access services
# Airflow UI:  http://localhost:8080  (admin / admin)
# API:         http://localhost:8000
# API docs:    http://localhost:8000/docs
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness check |
| GET | `/filings` | List filings with sentiment (filter by ticker, form type) |
| GET | `/filings/{id}` | Get single filing |
| GET | `/sentiment/trend` | Sentiment over time for a ticker |
| GET | `/sentiment/summary` | Aggregate sentiment breakdown |

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
ruff check src/ dags/ tests/
mypy src/ --ignore-missing-imports
```

## Azure Deployment

Set the following GitHub Actions secrets:

| Secret | Description |
|--------|-------------|
| `AZURE_CREDENTIALS` | Service principal JSON from `az ad sp create-for-rbac` |
| `AZURE_RESOURCE_GROUP` | Resource group name |
| `ACR_LOGIN_SERVER` | Azure Container Registry login server |
| `ACR_USERNAME` | ACR username |
| `ACR_PASSWORD` | ACR password |

On merge to `main`, GitHub Actions will build, push, and deploy automatically.

## Stack

**Languages:** Python 3.11  
**Pipeline:** Apache Airflow 2.9, PostgreSQL 16, SQLAlchemy 2.0  
**ML:** PyTorch, HuggingFace Transformers, ProsusAI/finbert  
**API:** FastAPI, Uvicorn, Pydantic v2  
**Infra:** Docker, Azure Container Apps, Azure Container Registry, Azure Database for PostgreSQL  
**CI/CD:** GitHub Actions  
