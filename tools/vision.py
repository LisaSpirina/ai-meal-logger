# tools/vision.py
import base64
import json
import os
from pathlib import Path
from google import genai
from dotenv import load_dotenv
from config import GEMINI_MODEL

load_dotenv()

client = genai.Client(api_key=os.environ["GOOGLE_AI_API_KEY"])

def identify_food(image_path: str) -> list[dict]:
    """Returns e.g. [{"name": "grilled chicken breast", "confidence": 0.82}, ...]"""
    image_data = Path(image_path).read_bytes()

    prompt = """You are a nutrition expert analyzing a meal photo.
    Identify every distinct food item visible.

    IMPORTANT: Use simple, common food names that match USDA database entries.
    - Good: "salmon fillet", "cherry tomatoes", "feta cheese", "lettuce"
    - Bad: "pan-seared salmon with black pepper", "teriyaki pre-seasoned salmon fillets"
    - Strip cooking methods, seasonings, and brand names from the food name
    - Use the simplest possible name: "salmon" not "seasoned salmon fillet"

    Respond ONLY with a valid JSON array, no explanation, no markdown:
    [{"name": "simple food name", "confidence": 0.0_to_1.0}]"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            prompt,
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_data).decode()}}
        ]
    )

    raw = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(raw)