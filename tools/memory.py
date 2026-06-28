# tools/memory.py
import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path
import tools.db as db

logger = logging.getLogger(__name__)

DB_PATH = Path("data/meals.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def get_recent_meals(user_id: int, limit: int = 5) -> list[dict]:
    """
    Returns the last `limit` meals with their items.
    Oldest first so it reads chronologically in a prompt.

    [
        {
            "timestamp": "2026-06-27 12:34:00",
            "total_kcal": 650.0,
            "total_protein_g": 48.0,
            "items": [
                {"name": "grilled chicken", "grams": 150, "kcal": 247.5},
                ...
            ]
        },
        ...
    ]
    """
    with _conn() as conn:
        meals = conn.execute(
            """
            SELECT id, timestamp, total_kcal, total_protein_g
            FROM meal_log
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

        result = []
        for meal in meals:
            items = conn.execute(
                """
                SELECT name, grams, kcal_per_100g
                FROM meal_items
                WHERE meal_id = ?
                """,
                (meal["id"],),
            ).fetchall()

            result.append({
                "timestamp":       meal["timestamp"],
                "total_kcal":      meal["total_kcal"],
                "total_protein_g": meal["total_protein_g"],
                "items": [
                    {
                        "name":  i["name"],
                        "grams": i["grams"],
                        "kcal":  round(i["kcal_per_100g"] * i["grams"] / 100, 1),
                    }
                    for i in items
                ],
            })

    return list(reversed(result))


def format_memory_block(user_id: int, limit: int = 5) -> str:
    """
    Returns a prompt-ready string of recent meals + today's goal progress.
    Inject this into the agent system prompt in react_loop.py.

    Example:
        Past meals (most recent last):
        - 2026-06-26 08:10 | oatmeal (200g, 140 kcal), banana (120g, 107 kcal) | Total: 247 kcal
        - 2026-06-27 12:34 | grilled chicken (150g, 248 kcal), rice (180g, 234 kcal) | Total: 650 kcal

        Today's progress: 897 kcal eaten / 2000 kcal goal (1103 remaining)
        Protein today: 48.0g / 150g goal
    """
    meals = get_recent_meals(user_id, limit=limit)
    today = db.get_today_summary(user_id)
    goals = db.get_goals(user_id)

    lines = []

    if not meals:
        lines.append("No previous meals logged.")
    else:
        lines.append("Past meals (most recent last):")
        for meal in meals:
            items_str = ", ".join(
                f"{i['name']} ({i['grams']:.0f}g, {i['kcal']:.0f} kcal)"
                for i in meal["items"]
            )
            dt = meal["timestamp"][:16]
            lines.append(
                f"- {dt} | {items_str} | Total: {meal['total_kcal']:.0f} kcal"
            )

    lines.append("")
    lines.append(
        f"Today's progress: {today['total_kcal']:.0f} kcal eaten"
        f" / {goals['daily_kcal']:.0f} kcal goal"
        f" ({today['kcal_remaining']:.0f} remaining)"
    )
    lines.append(
        f"Protein today: {today['total_protein_g']:.1f}g"
        f" / {goals['daily_protein_g']:.0f}g goal"
    )

    return "\n".join(lines)