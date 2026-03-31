from setuptools import setup, find_packages

setup(
    name="stocksense",
    version="2.0.0",
    packages=find_packages(),
    install_requires=[
        "yfinance>=0.2.40",
        "finnhub-python>=2.4.19",
        "pandas>=2.2.3",
        "python-dotenv>=1.0.1",
        "sqlalchemy>=2.0.0",
        "psycopg2-binary>=2.9.9",
        "fastapi>=0.111.0",
        "uvicorn[standard]>=0.29.0",
        "pydantic>=2.7.0",
        "requests>=2.31.0",
        "torch>=2.2.0",
        "transformers>=4.40.0",
    ],
    author="Justin Cheng",
    description="Event-driven SEC filing intelligence pipeline with FinBERT sentiment analysis.",
    python_requires=">=3.11",
)