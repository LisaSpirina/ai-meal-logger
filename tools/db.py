# db.py
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("data/meals.db")


@contextmanager
def _conn():
    """Yield a connection with row_factory and auto-commit/rollback."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def ensure_user(user_id: int, first_name: str) -> None:
    """Insert user if not present. Safe to call on every message."""
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, first_name, created_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET first_name = excluded.first_name
            """,
            (user_id, first_name),
        )
        conn.execute(
            """
            INSERT INTO goals (user_id, daily_kcal, daily_protein_g)
            VALUES (?, 2000, 150)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id,),
        )


def set_goals(user_id: int, kcal_goal: float, protein_goal: float) -> None:
    """Upsert daily calorie and protein targets for a user."""
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO goals (user_id, daily_kcal, daily_protein_g)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE
                SET daily_kcal      = excluded.daily_kcal,
                    daily_protein_g = excluded.daily_protein_g
            """,
            (user_id, kcal_goal, protein_goal),
        )


def get_goals(user_id: int) -> dict:
    """
    Returns {"daily_kcal": float, "daily_protein_g": float}.
    Falls back to defaults if user has no goals row yet.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT daily_kcal, daily_protein_g FROM goals WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return {"daily_kcal": 2000.0, "daily_protein_g": 150.0}
    return dict(row)


# ---------------------------------------------------------------------------
# Meals
# ---------------------------------------------------------------------------

def save_meal(
    user_id: int,
    image_path: str,
    summary: str,
    items: list[dict],
) -> int:
    """
    Persist one meal and its food items to meal_log + meal_items.

    `items` is the collected_items list from react_loop, each dict may have:
        name, grams, kcal_per_100g, protein_g, fat_g, carbs_g, confidence

    Returns the new meal_log id.
    """
    total_kcal = total_protein = total_fat = total_carbs = 0.0
    for item in items:
        grams = item.get("grams", 100)
        factor = grams / 100
        total_kcal    += item.get("kcal_per_100g", 0) * factor
        total_protein += item.get("protein_g", 0)     * factor
        total_fat     += item.get("fat_g", 0)         * factor
        total_carbs   += item.get("carbs_g", 0)       * factor

    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO meal_log
                (user_id, timestamp, image_path, summary,
                 total_kcal, total_protein_g, total_fat_g, total_carbs_g)
            VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?)
            """,
            (user_id, image_path, summary,
             total_kcal, total_protein, total_fat, total_carbs),
        )
        meal_id = cur.lastrowid

        conn.executemany(
            """
            INSERT INTO meal_items
                (meal_id, name, grams, kcal_per_100g,
                 protein_g, fat_g, carbs_g, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    meal_id,
                    item.get("name"),
                    item.get("grams", 100),
                    item.get("kcal_per_100g", 0),
                    item.get("protein_g", 0),
                    item.get("fat_g", 0),
                    item.get("carbs_g", 0),
                    item.get("confidence"),
                )
                for item in items
            ],
        )

    logger.info(
        "Saved meal %d for user %d (%d items, %.0f kcal)",
        meal_id, user_id, len(items), total_kcal,
    )
    return meal_id


# ---------------------------------------------------------------------------
# Summaries  (raw data — consumed by memory.py and weekly_insights.py)
# ---------------------------------------------------------------------------

def get_today_summary(user_id: int) -> dict:
    """
    Returns totals for meals logged today (UTC) plus goal progress.

    {
        "meals_count": int,
        "total_kcal": float,
        "total_protein_g": float,
        "total_fat_g": float,
        "total_carbs_g": float,
        "daily_kcal": float,
        "daily_protein_g": float,
        "kcal_remaining": float,
        "protein_remaining": float,
    }
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with _conn() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*)                          AS meals_count,
                COALESCE(SUM(total_kcal),      0) AS total_kcal,
                COALESCE(SUM(total_protein_g), 0) AS total_protein_g,
                COALESCE(SUM(total_fat_g),     0) AS total_fat_g,
                COALESCE(SUM(total_carbs_g),   0) AS total_carbs_g
            FROM meal_log
            WHERE user_id = ? AND DATE(timestamp) = ?
            """,
            (user_id, today),
        ).fetchone()

    goals = get_goals(user_id)
    totals = dict(row)
    totals["daily_kcal"]        = goals["daily_kcal"]
    totals["daily_protein_g"]   = goals["daily_protein_g"]
    totals["kcal_remaining"]    = max(0.0, goals["daily_kcal"]      - totals["total_kcal"])
    totals["protein_remaining"] = max(0.0, goals["daily_protein_g"] - totals["total_protein_g"])
    return totals


def get_week_summary(user_id: int) -> list[dict]:
    """
    Returns one row per day for the past 7 days (including today).

    [{"date": "2026-06-27", "meals_count": 2, "total_kcal": 1800, ...}, ...]
    Sorted oldest → newest. Days with no meals are omitted.
    """
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT
                DATE(timestamp)                       AS date,
                COUNT(*)                              AS meals_count,
                COALESCE(SUM(total_kcal),      0)     AS total_kcal,
                COALESCE(SUM(total_protein_g), 0)     AS total_protein_g,
                COALESCE(SUM(total_fat_g),     0)     AS total_fat_g,
                COALESCE(SUM(total_carbs_g),   0)     AS total_carbs_g
            FROM meal_log
            WHERE user_id = ?
              AND DATE(timestamp) >= DATE('now', '-6 days')
            GROUP BY DATE(timestamp)
            ORDER BY DATE(timestamp) ASC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_user_ids() -> list[int]:
    """Returns all user_ids. Used by the weekly insight job to fan out."""
    with _conn() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
    return [r["user_id"] for r in rows]


def get_meal_history(user_id: int, limit: int = 10) -> list[dict]:
    """
    Returns the last `limit` meals for display to the user.

    [{"timestamp": "2026-06-27 19:38", "summary": "...", "total_kcal": 268, "total_protein_g": 3.5}, ...]
    """
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, summary, total_kcal, total_protein_g
            FROM meal_log
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]