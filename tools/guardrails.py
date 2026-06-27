# tools/guardrails.py
import base64
import json
import os
from pathlib import Path
from google import genai
from config import GEMINI_MODEL

# REMOVED: client = genai.Client(...) from module level

ISSUE_MESSAGES = {
    "not_food": "That doesn't look like a food photo. Send me a picture of your meal! 🍽",
    "raw_food": "I only log prepared meals. Send me a photo after it's cooked! 🍳",
    "too_blurry": "The photo is too blurry — try again with better lighting or closer focus. 📷",
    "too_dark": "The photo is too dark to see the food clearly. Try in better lighting. 💡",
    "packaged": "I can't log unopened packaged food. Show me the actual meal! 🥡",
    "multiple_issues": "I couldn't read that photo clearly. Try a clearer shot of your meal. 📸",
    "none": "Image looks valid.",
}

VALIDATION_PROMPT = """You are a food photo validator. Analyze this image and respond with ONLY valid JSON:

{
  "is_valid": true or false,
  "reason": "brief reason if invalid, empty string if valid",
  "issue": "one of: not_food, raw_food, too_blurry, too_dark, packaged, multiple_issues, none"
}

Reject the image if ANY of these are true:
- Not a food photo (people, landscapes, objects, screenshots, memes)
- Contains only raw/uncooked meat, fish, or poultry (we log meals, not ingredients)
- Image is too blurry or low quality to identify food items
- Image is too dark to see food clearly
- Packaged/unopened food with no visible meal (e.g. just a candy wrapper)

Accept if:
- It shows a prepared/cooked meal or snack, even if imperfect quality
- It shows raw vegetables, fruits or other ingredients that are clearly identifiable
- It shows a drink (coffee, juice, smoothie etc.)
"""


def validate_image(image_path: str) -> dict:
    """
    Returns {"is_valid": bool, "reason": str, "issue": str}
    Raises RuntimeError on API failure.
    """
    client = genai.Client(api_key=os.environ["GOOGLE_AI_API_KEY"])  # ← moved here
    try:
        image_data = Path(image_path).read_bytes()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                VALIDATION_PROMPT,
                {"inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(image_data).decode()
                }}
            ]
        )
    except Exception as exc:
        raise RuntimeError(f"Validation API call failed: {exc}") from exc

    try:
        cleaned = response.text.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ValueError(f"Could not parse validation response: {response.text}") from exc


def get_rejection_message(issue: str) -> str:
    """Returns a user-friendly message for a given issue type."""
    return ISSUE_MESSAGES.get(issue, "I couldn't process that photo. Please try again.")