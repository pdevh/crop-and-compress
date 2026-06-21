import os
from dotenv import load_dotenv
from google import genai

load_dotenv('/Users/philipp/Coding/crop-and-compress/.env')
api_key = os.environ.get("GEMINI_API_KEY")

client = genai.Client(api_key=api_key)
for model in client.models.list():
    if "image" in model.name or "flash" in model.name or "gemini" in model.name:
        print(model.name)
