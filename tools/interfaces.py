# tools/interfaces.py

def identify_food(image_path: str) -> list[dict]:
    """
    Takes a local path to a food photo.
    Returns e.g. [{"name": "grilled chicken", "confidence": 0.85}]
    Teammate implements this in tools/vision.py
    """
    raise NotImplementedError

def lookup_nutrition(food_name: str) -> dict:
    """
    Takes a food name string.
    Returns e.g. {"name": "chicken breast", "kcal_per_100g": 165,
                  "protein_g": 31, "fat_g": 3.6, "carbs_g": 0}
    Teammate implements this in tools/nutrition.py
    """
    raise NotImplementedError

def estimate_portion(food_name: str) -> dict:
    """
    Takes a food name.
    Returns e.g. {"grams": 150, "confidence": "medium"}
    You implement this in tools/portion.py
    """
    raise NotImplementedError

def save_entry(user_id: int, items: list[dict], summary: str) -> int:
    """
    Saves a meal to the database.
    Returns the new meal_log row id.
    Teammate implements this in tools/db.py
    """
    raise NotImplementedError

def retrieve_episodes(user_id: int, query: str, k: int = 5) -> list[dict]:
    """
    Finds the k most similar past meals to the query string.
    Returns a list of episode dicts with summary and nutrition.
    Teammate implements this in tools/memory.py
    """
    raise NotImplementedError