import os
from pathlib import Path
from dotenv import load_dotenv
import requests

load_dotenv(Path(__file__).resolve().parent / ".env")
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("OPENAI_API_KEY is not set")

response = requests.get(
    "https://api.openai.com/v1/models",
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=30,
)
response.raise_for_status()
for model in response.json().get("data", []):
    model_id = model.get("id", "")
    if "image" in model_id:
        print(model_id)
