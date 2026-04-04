# src/jobs/score_trigger.py
import sys

import requests

resp = requests.post(
    "https://stocksense-api.delightfultree-af000461.centralus.azurecontainerapps.io/score/trigger",
    timeout=3600,
)
resp.raise_for_status()
result = resp.json()
print(f"Scoring complete: {result}")
sys.exit(0)