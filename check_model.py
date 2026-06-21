import os
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv(Path(__file__).resolve().parent / ".env")
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("OPENAI_API_KEY is not set")

response = requests.get(
    "https://api.openai.com/v1/models/gpt-image-2",
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=30,
)
response.raise_for_status()
model = response.json()
print(f"Model: {model.get('id')}")
print(f"Object: {model.get('object')}")
