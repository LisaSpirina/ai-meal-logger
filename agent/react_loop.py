# agent/react_loop.py
import json
import logging
import os
from pathlib import Path

from google import genai

from tools.vision import identify_food
from tools.nutrition import lookup_nutrition
from config import GEMINI_MODEL

logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.environ["GOOGLE_AI_API_KEY"])

MAX_STEPS = 12

SYSTEM_PROMPT = """You are a meal-logging agent. You have these tools available:

1. identify_food() -- analyzes the meal photo, returns a list of food items with confidence scores. No arguments needed, the image is already provided.
2. lookup_nutrition(food_name: str) -- returns nutrition per 100g for a named food from USDA data.
3. estimate_portion(food_name: str) -- returns an estimated portion size in grams for a named food.
4. finish(summary: str) -- call this when you have identified all foods, looked up nutrition, and estimated portions for each. Pass a final human-readable summary as the argument.

At each step, respond with ONLY valid JSON, no markdown, no explanation:
{"thought": "your reasoning", "action": "tool_name", "action_input": {"arg_name": "value"}}

For identify_food, action_input should be {}.
For finish, action_input should be {"summary": "..."}.

Call identify_food first. Then for each food found, call lookup_nutrition and estimate_portion before calling finish.
"""


def _call_tool(action: str, action_input: dict, image_path: str) -> dict:
    if action == "identify_food":
        return {"foods": identify_food(image_path)}

    if action == "lookup_nutrition":
        food_name = action_input.get("food_name")
        if not food_name:
            raise ValueError("lookup_nutrition requires 'food_name'")
        return lookup_nutrition(food_name)

    if action == "estimate_portion":
        food_name = action_input.get("food_name")
        if not food_name:
            raise ValueError("estimate_portion requires 'food_name'")
        # TODO: swap for tools.portion.estimate_portion once teammate finishes it
        return {"grams": 150, "confidence": "medium"}

    raise ValueError(f"Unknown action: {action}")


def _parse_step(raw_text: str) -> dict:
    cleaned = raw_text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Agent returned invalid JSON: {raw_text!r}") from exc


def run_meal_logging(user_id: int, image_path: str) -> str:
    """Runs the ReAct loop for one photo. Returns the final reply text."""
    transcript = [f"System: {SYSTEM_PROMPT}"]
    collected_items: list[dict] = []

    for step_num in range(1, MAX_STEPS + 1):
        prompt = "\n".join(transcript) + "\n\nWhat is your next thought and action?"

        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[prompt],
            )
        except Exception as exc:
            logger.error("Agent LLM call failed at step %d: %s", step_num, exc)
            return "Sorry, I'm having trouble thinking right now. Please try again."

        try:
            step = _parse_step(response.text)
        except ValueError as exc:
            logger.error("Step %d parse error: %s", step_num, exc)
            transcript.append(f"Observation: Error - your last response wasn't valid JSON. Try again.")
            continue

        action = step.get("action")
        action_input = step.get("action_input", {})
        logger.info("Step %d | Thought: %s | Action: %s(%s)",
                    step_num, step.get("thought"), action, action_input)

        if action == "finish":
            summary = action_input.get("summary", "Meal logged.")
            return f"🍽 {summary}"

        try:
            observation = _call_tool(action, action_input, image_path)
        except ValueError as exc:
            observation = {"error": str(exc)}
        except RuntimeError as exc:
            observation = {"error": f"Tool failed: {exc}"}

        if action == "identify_food" and "foods" in observation:
            for food in observation["foods"]:
                collected_items.append({"name": food["name"]})
        elif action == "lookup_nutrition" and "error" not in observation:
            _merge_into_collected(collected_items, observation)
        elif action == "estimate_portion" and "error" not in observation:
            _merge_into_collected(collected_items, observation)

        transcript.append(f"Action: {action}({action_input})")
        transcript.append(f"Observation: {json.dumps(observation)}")

    logger.warning("Agent hit MAX_STEPS without finishing for user %s", user_id)
    return _format_final_reply("Meal logged (partial analysis).", collected_items)


def _merge_into_collected(items: list[dict], data: dict) -> None:
    """Merges a tool observation into the most recently active collected item."""
    name = data.get("name", "")
    # Try exact substring match first
    for item in items:
        item_name = item.get("name", "").lower()
        data_name = name.lower()
        if item_name in data_name or data_name in item_name:
            item.update(data)
            return
    # Fallback: merge into the last item that's missing nutrition data
    for item in reversed(items):
        if "kcal_per_100g" not in item:
            item.update(data)
            return
    # Last resort: update most recent item
    if items:
        items[-1].update(data)


def _format_final_reply(summary: str, items: list[dict]) -> str:
    if not items:
        return summary

    lines = [f"🍽 {summary}\n"]
    total_kcal = 0.0
    for item in items:
        grams = item.get("grams", 100)
        kcal_per_100g = item.get("kcal_per_100g", 0)
        kcal = kcal_per_100g * grams / 100
        total_kcal += kcal
        lines.append(f"• {item.get('name', 'unknown')} (~{grams}g) — {kcal:.0f} kcal")

    lines.append(f"\n📊 Total: ~{total_kcal:.0f} kcal")
    return "\n".join(lines)