# tools/portion.py

# Default portion sizes in grams, by food category keyword.
# Simple heuristic — good enough for demo, improves with episodic memory over time.

PORTION_DEFAULTS: dict[str, int] = {
    # Proteins
    "chicken": 150,
    "beef": 150,
    "pork": 150,
    "lamb": 150,
    "fish": 130,
    "salmon": 130,
    "tuna": 130,
    "shrimp": 100,
    "egg": 55,
    "hard-boiled": 50,
    "boiled egg": 50,
    "tofu": 150,
    # Carbs
    "rice": 180,
    "pasta": 180,
    "bread": 60,
    "potato": 200,
    "noodle": 180,
    "oat": 80,
    # Vegetables
    "salad": 100,
    "broccoli": 100,
    "carrot": 80,
    "spinach": 60,
    "tomato": 100,
    "cucumber": 80,
    "pepper": 80,
    "onion": 50,
    "dill": 5,       # garnish
    "parsley": 5,    # garnish
    "garnish": 5,
    # Dairy
    "cheese": 40,
    "yogurt": 150,
    "milk": 200,
    "butter": 10,
    # Fruits
    "apple": 180,
    "banana": 120,
    "orange": 150,
    "berries": 80,
    # Sauces / extras
    "sauce": 30,
    "gravy": 50,
    "oil": 10,
    "dressing": 20,
}

DEFAULT_PORTION = 150  # fallback if no keyword matches


def estimate_portion(food_name: str) -> dict:
    """
    Returns {"grams": int, "confidence": "low"|"medium"|"high"}
    Uses keyword matching against food name — no API call needed.
    """
    food_lower = food_name.lower()

    for keyword, grams in PORTION_DEFAULTS.items():
        if keyword in food_lower:
            confidence = "medium"
            # Garnishes are high confidence — we know exactly how much dill goes on a plate
            if keyword in ("dill", "parsley", "garnish", "butter", "oil"):
                confidence = "high"
            return {"grams": grams, "confidence": confidence}

    return {"grams": DEFAULT_PORTION, "confidence": "low"}