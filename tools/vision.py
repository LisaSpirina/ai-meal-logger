# tools/vision.py
import base64
import json
import os
from pathlib import Path
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.environ["GOOGLE_AI_API_KEY"])

def identify_food(image_path: str) -> list[dict]:
    """Returns e.g. [{"name": "grilled chicken breast", "confidence": 0.82}, ...]"""
    image_data = Path(image_path).read_bytes()

    prompt = """Look at this food image and identify all food items visible.
Respond ONLY with a valid JSON array, no explanation, no markdown. Example:
[{"name": "grilled chicken breast", "confidence": 0.85}, {"name": "white rice", "confidence": 0.90}]"""

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=[
            prompt,
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_data).decode()}}
        ]
    )

    raw = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(raw)