# tools/nutrition.py
import os
import requests

NUTRIENT_IDS = {
    1008: "kcal_per_100g",  # was 208
    1003: "protein_g",       # was 203
    1004: "fat_g",           # was 204
    1005: "carbs_g",         # was 205
}

_cache: dict[str, dict] = {}

def lookup_nutrition(food_name: str) -> dict:
    """Returns {"fdc_id", "name", "kcal_per_100g", "protein_g", "fat_g", "carbs_g"}"""
    if food_name in _cache:
        return _cache[food_name]

    api_key = os.environ["USDA_API_KEY"]
    resp = requests.get(
        "https://api.nal.usda.gov/fdc/v1/foods/search",
        params={"query": food_name, "api_key": api_key, "pageSize": 1},
        timeout=10,
    )
    resp.raise_for_status()
    foods = resp.json().get("foods", [])

    if not foods:
        raise ValueError(f"No USDA match for '{food_name}'")

    food = foods[0]
    nutrients = {n["nutrientId"]: n["value"] for n in food.get("foodNutrients", [])}

    result = {
        "fdc_id": food["fdcId"],
        "name": food["description"],
        **{label: nutrients.get(nid, 0.0) for nid, label in NUTRIENT_IDS.items()}
    }
    _cache[food_name] = result
    return result


