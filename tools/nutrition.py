# tools/nutrition.py
import os
import requests

NUTRIENT_IDS = {
    1008: "kcal_per_100g",
    1003: "protein_g",
    1004: "fat_g",
    1005: "carbs_g",
}

_cache: dict[str, dict] = {}

def lookup_nutrition(food_name: str) -> dict:
    """Returns {"fdc_id", "name", "kcal_per_100g", "protein_g", "fat_g", "carbs_g"}"""
    if food_name in _cache:
        return _cache[food_name]

    api_key = os.environ["USDA_API_KEY"]

    try:
        resp = requests.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={"query": food_name, "api_key": api_key, "pageSize": 1},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"USDA API request failed for '{food_name}': {exc}") from exc

    try:
        foods = resp.json().get("foods", [])
    except ValueError as exc:  # invalid JSON in response
        raise RuntimeError(f"USDA returned malformed response for '{food_name}': {exc}") from exc

    if not foods:
        raise ValueError(f"No USDA match for '{food_name}'")

    food = foods[0]
    nutrients = {
        n["nutrientId"]: n.get("value", 0.0)
        for n in food.get("foodNutrients", [])
        if "nutrientId" in n
    }

    result = {
        "fdc_id": food.get("fdcId"),
        "name": food.get("description", food_name),
        **{label: nutrients.get(nid, 0.0) for nid, label in NUTRIENT_IDS.items()}
    }
    _cache[food_name] = result
    return result