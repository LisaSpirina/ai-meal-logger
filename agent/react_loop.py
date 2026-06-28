# agent/react_loop.py
import json
import logging
import os
import base64
from pathlib import Path

from google import genai

from tools.vision import identify_food
from tools.nutrition import lookup_nutrition
from tools.portion import estimate_portion
from tools.guardrails import validate_image, get_rejection_message
from tools.memory import format_memory_block
from config import GEMINI_MODEL

logger = logging.getLogger(__name__)

MAX_STEPS = 15

SYSTEM_PROMPT = """You are a meal-logging agent. You have these tools available:

1. validate_image() -- ALWAYS call this first. Checks if the photo is a valid food image.
2. identify_food() -- analyzes the meal photo, returns food items. Only call if validate_image returns is_valid=true.
3. lookup_nutrition(food_name: str) -- returns nutrition per 100g for a named food from USDA data.
4. estimate_portion(food_name: str) -- returns an estimated portion size in grams for a named food.
5. finish(summary: str) -- call this when done. If image is invalid, call finish immediately with a friendly explanation.

At each step, respond with ONLY valid JSON, no markdown, no explanation:
{"thought": "your reasoning", "action": "tool_name", "action_input": {"arg_name": "value"}}

For validate_image, action_input should be {}.
For identify_food, action_input should be {}.
For finish, action_input should be {"summary": "..."}.

STRICT ORDER AND RULES:
- Step 1: always validate_image, no exceptions.
- If is_valid=false: call finish immediately with a friendly explanation. Do not call any other tool.
- If is_valid=true: call identify_food next.
- After identify_food: select the top 5 items by confidence score only. Ignore the rest.
- Ignore garnishes, drinks, and condiments unless they are a primary component of the meal.
- For each of the top 5 items, call lookup_nutrition IMMEDIATELY followed by estimate_portion before moving to the next item.
- Do not re-examine or re-confirm items you have already processed. Move directly to the next action.
- After all items are processed, call finish once with the full summary.
- finish summary must include: each food item name, estimated grams, kcal, protein, fat, carbs, and a total line.
- Keep thoughts short — one sentence maximum.

FOOD NAME RULES for lookup_nutrition:
- Always use the simplest possible name that matches common USDA database entries.
- Strip all cooking methods, seasonings, brand names, and descriptors.
- Good: "salmon", "feta cheese", "cherry tomatoes", "lettuce", "cucumber"
- Bad: "pan-seared salmon with black pepper", "crumbled feta cheese", "teriyaki pre-seasoned salmon fillets"
- If unsure, use a single word: "salmon" not "seasoned salmon fillet"
"""

TEXT_SYSTEM_PROMPT = """You are a meal-logging agent. The user has described their meal in text — there is no photo.
You have these tools available:

1. lookup_nutrition(food_name: str) -- returns nutrition per 100g for a named food from USDA data.
2. estimate_portion(food_name: str) -- returns an estimated portion size in grams for a named food.
3. finish(summary: str) -- call this when you have looked up nutrition and estimated portions for every food item mentioned.

At each step, respond with ONLY valid JSON, no markdown, no explanation:
{"thought": "your reasoning", "action": "tool_name", "action_input": {"arg_name": "value"}}

For each food item the user mentioned, call lookup_nutrition and estimate_portion before calling finish.
"""


def _build_system_prompt(user_id: int) -> str:
    """Builds the system prompt with episodic memory injected."""
    try:
        memory = format_memory_block(user_id)
    except Exception as exc:
        logger.warning("Could not load memory for user %s: %s", user_id, exc)
        memory = "No previous meals logged."
    return SYSTEM_PROMPT + f"\n\nUser's meal history and today's progress:\n{memory}"


def _call_tool(action: str, action_input: dict, image_path: str | None) -> dict:
    if action == "validate_image":
        return validate_image(image_path)

    if action == "identify_food":
        try:
            foods = identify_food(image_path)
        except (ValueError, RuntimeError) as exc:
            raise RuntimeError(f"identify_food failed: {exc}") from exc
        foods_sorted = sorted(
            foods,
            key=lambda x: x.get("confidence", 0),
            reverse=True
        )[:5]
        return {"foods": foods_sorted}

    if action == "lookup_nutrition":
        food_name = action_input.get("food_name")
        if not food_name:
            raise ValueError("lookup_nutrition requires 'food_name'")
        try:
            return lookup_nutrition(food_name)
        except ValueError:
            words = food_name.split()
            simple = " ".join(words[:2]) if len(words) > 2 else food_name
            if simple != food_name:
                try:
                    return lookup_nutrition(simple)
                except ValueError:
                    pass
            if len(words) > 1:
                try:
                    return lookup_nutrition(words[0])
                except ValueError:
                    pass
            raise ValueError(f"No USDA match for '{food_name}'")

    if action == "estimate_portion":
        food_name = action_input.get("food_name")
        if not food_name:
            raise ValueError("estimate_portion requires 'food_name'")
        return estimate_portion(food_name)

    raise ValueError(f"Unknown action: {action}")


def _parse_step(raw_text: str) -> dict:
    cleaned = raw_text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent returned invalid JSON: {raw_text!r}") from exc


def _merge_into_collected(items: list[dict], data: dict) -> None:
    """Merges nutrition/portion data into the matching collected item."""
    name = data.get("name", "")
    for item in items:
        item_name = item.get("name", "").lower()
        data_name = name.lower()
        if item_name in data_name or data_name in item_name:
            original_name = item.get("name")
            item.update(data)
            item["name"] = original_name  # preserve vision name
            return
    for item in reversed(items):
        if "kcal_per_100g" not in item:
            original_name = item.get("name")
            item.update(data)
            item["name"] = original_name
            return
    if items:
        original_name = items[-1].get("name")
        items[-1].update(data)
        items[-1]["name"] = original_name


def _format_reply_from_collected(summary: str, items: list[dict]) -> str:
    """Clean formatted reply using collected_items data."""
    if not items:
        return f"🍽 {summary}"

    lines = ["🍽 *Meal Analysis*\n"]
    total_kcal = total_protein = total_fat = total_carbs = 0.0

    for item in items:
        grams = item.get("grams", 100)
        kcal = item.get("kcal_per_100g", 0) * grams / 100
        protein = item.get("protein_g", 0) * grams / 100
        fat = item.get("fat_g", 0) * grams / 100
        carbs = item.get("carbs_g", 0) * grams / 100
        total_kcal += kcal
        total_protein += protein
        total_fat += fat
        total_carbs += carbs
        lines.append(
            f"• *{item.get('name', 'unknown')}* (~{grams}g)\n"
            f"  {kcal:.0f} kcal | {protein:.1f}g protein | "
            f"{fat:.1f}g fat | {carbs:.1f}g carbs"
        )

    lines.append(
        f"\n📊 *Total*\n"
        f"{total_kcal:.0f} kcal | {total_protein:.1f}g protein | "
        f"{total_fat:.1f}g fat | {total_carbs:.1f}g carbs"
    )
    return "\n".join(lines)


def _format_final_reply(summary: str, items: list[dict]) -> str:
    """Fallback formatter for MAX_STEPS case."""
    return _format_reply_from_collected(summary, items)


def run_meal_logging(user_id: int, image_path: str) -> tuple[str, list[dict]]:
    """Runs the ReAct loop for one photo. Returns (reply_text, collected_items)."""
    client = genai.Client(api_key=os.environ["GOOGLE_AI_API_KEY"])
    system_prompt = _build_system_prompt(user_id)
    transcript = [f"System: {system_prompt}"]
    collected_items: list[dict] = []
    last_validation: dict = {}

    image_data = Path(image_path).read_bytes()
    image_b64 = base64.b64encode(image_data).decode()

    for step_num in range(1, MAX_STEPS + 1):
        prompt = "\n".join(transcript) + "\n\nWhat is your next thought and action?"

        try:
            contents = (
                [prompt, {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}]
                if step_num == 1
                else [prompt]
            )
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
            )
        except Exception as exc:
            logger.error("Agent LLM call failed at step %d: %s", step_num, exc)
            return "Sorry, I'm having trouble thinking right now. Please try again.", []

        try:
            step = _parse_step(response.text)
        except ValueError as exc:
            logger.error("Step %d parse error: %s", step_num, exc)
            transcript.append("Observation: Error - your last response wasn't valid JSON. Try again.")
            continue

        action = step.get("action")
        action_input = step.get("action_input", {})
        logger.info("Step %d | Thought: %s | Action: %s(%s)",
                    step_num, step.get("thought"), action, action_input)

        if action == "finish":
            if last_validation and not last_validation.get("is_valid", True):
                issue = last_validation.get("issue", "none")
                return f"❌ {get_rejection_message(issue)}", []
            summary = action_input.get("summary", "Meal logged.")
            return _format_reply_from_collected(summary, collected_items), collected_items

        try:
            observation = _call_tool(action, action_input, image_path)
        except ValueError as exc:
            observation = {"error": str(exc)}
        except RuntimeError as exc:
            observation = {"error": f"Tool failed: {exc}"}

        if action == "validate_image":
            last_validation = observation
        elif action == "identify_food" and "foods" in observation:
            for food in observation["foods"]:
                collected_items.append({
                    "name": food["name"],
                    "confidence": food.get("confidence"),
                })
        elif action == "lookup_nutrition" and "error" not in observation:
            _merge_into_collected(collected_items, observation)
        elif action == "estimate_portion" and "error" not in observation:
            _merge_into_collected(collected_items, observation)

        transcript.append(f"Action: {action}({action_input})")
        transcript.append(f"Observation: {json.dumps(observation)}")

    logger.warning("Agent hit MAX_STEPS without finishing for user %s", user_id)
    return _format_final_reply("Meal logged (partial analysis).", collected_items), collected_items


def run_text_logging(user_id: int, meal_text: str) -> tuple[str, list[dict]]:
    """Runs the ReAct loop for a text meal description. Returns (reply_text, collected_items)."""
    client = genai.Client(api_key=os.environ["GOOGLE_AI_API_KEY"])

    try:
        memory = format_memory_block(user_id)
    except Exception as exc:
        logger.warning("Could not load memory for user %s: %s", user_id, exc)
        memory = "No previous meals logged."

    system_prompt = (
        TEXT_SYSTEM_PROMPT
        + f"\n\nUser's meal history and today's progress:\n{memory}"
        + f"\n\nThe user says they ate: {meal_text}"
    )

    transcript = [f"System: {system_prompt}"]
    collected_items: list[dict] = []

    for word in meal_text.split(" and "):
        name = word.strip()
        if name:
            collected_items.append({"name": name})

    for step_num in range(1, MAX_STEPS + 1):
        prompt = "\n".join(transcript) + "\n\nWhat is your next thought and action?"

        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[prompt],
            )
        except Exception as exc:
            logger.error("Text agent LLM call failed at step %d: %s", step_num, exc)
            return "Sorry, I'm having trouble. Please try again.", collected_items

        try:
            step = _parse_step(response.text)
        except ValueError as exc:
            logger.error("Step %d parse error: %s", step_num, exc)
            transcript.append("Observation: Error - your last response wasn't valid JSON. Try again.")
            continue

        action = step.get("action")
        action_input = step.get("action_input", {})
        logger.info("Text step %d | Thought: %s | Action: %s(%s)",
                    step_num, step.get("thought"), action, action_input)

        if action == "finish":
            summary = action_input.get("summary", "Meal logged.")
            return _format_reply_from_collected(summary, collected_items), collected_items

        if action == "identify_food":
            transcript.append(
                "Observation: identify_food is not available for text logging. "
                "Use lookup_nutrition instead."
            )
            continue

        try:
            observation = _call_tool(action, action_input, image_path=None)
        except ValueError as exc:
            observation = {"error": str(exc)}
        except RuntimeError as exc:
            observation = {"error": f"Tool failed: {exc}"}

        if action == "lookup_nutrition" and "error" not in observation:
            _merge_into_collected(collected_items, observation)
        elif action == "estimate_portion" and "error" not in observation:
            _merge_into_collected(collected_items, observation)

        transcript.append(f"Action: {action}({action_input})")
        transcript.append(f"Observation: {json.dumps(observation)}")

    logger.warning("Text agent hit MAX_STEPS for user %s", user_id)
    return _format_final_reply("Meal logged (partial analysis).", collected_items), collected_items