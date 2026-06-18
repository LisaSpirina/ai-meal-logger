from dotenv import load_dotenv
load_dotenv()

from google import genai
import os, base64

client = genai.Client(api_key=os.environ["GOOGLE_AI_API_KEY"])

image_data = open("downloads/5978633940_44.jpg", "rb").read()

prompt = """Look at this food image and identify all food items visible.
Respond ONLY with a valid JSON array, no explanation, no markdown. Example:
[{"name": "grilled chicken breast", "confidence": 0.85}, {"name": "white rice", "confidence": 0.90}]"""

response = client.models.generate_content(
    model="gemma-4-26b-a4b-it",
    #model="gemini-2.5-flash-lite",
    contents=[
        prompt,
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_data).decode()}}
    ]
)
print(response.text)