import os
from dotenv import load_dotenv
from google import genai

load_dotenv('/Users/philipp/Coding/crop-and-compress/.env')
api_key = os.environ.get("GEMINI_API_KEY")

client = genai.Client(api_key=api_key)
model = client.models.get(model="gemini-2.5-flash-image")
print(f"Model: {model.name}")
print(f"Supported actions: {model.supported_actions}")
