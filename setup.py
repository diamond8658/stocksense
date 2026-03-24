from setuptools import setup, find_packages

setup(
    name="stock-ticker-sourcer",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "yfinance",
        "finnhub-python",
        "pandas>=2.2.3",
        "python-dotenv",
    ],
    author="Your Name",
    description="A modular framework for sourcing stock earnings and news.",
    python_requires=">=3.10", 
)