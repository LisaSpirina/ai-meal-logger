# tests/test_db.py
import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Test DB setup — use a temporary in-memory database for every test
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    first_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS goals (
    user_id         INTEGER PRIMARY KEY REFERENCES users(user_id),
    daily_kcal      REAL DEFAULT 2000,
    daily_protein_g REAL DEFAULT 150
);
CREATE TABLE IF NOT EXISTS meal_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(user_id),
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    image_path      TEXT,
    summary         TEXT,
    total_kcal      REAL DEFAULT 0,
    total_protein_g REAL DEFAULT 0,
    total_fat_g     REAL DEFAULT 0,
    total_carbs_g   REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meal_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_id       INTEGER NOT NULL REFERENCES meal_log(id),
    name          TEXT,
    grams         REAL DEFAULT 100,
    kcal_per_100g REAL DEFAULT 0,
    protein_g     REAL DEFAULT 0,
    fat_g         REAL DEFAULT 0,
    carbs_g       REAL DEFAULT 0,
    confidence    REAL
);
"""


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """
    Each test gets a fresh SQLite file in a temp directory.
    We monkeypatch tools.db.DB_PATH before importing any db functions
    so every test is fully isolated.
    """
    db_file = tmp_path / "test_meals.db"
    conn = sqlite3.connect(db_file)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

    monkeypatch.setattr("tools.db.DB_PATH", db_file)
    return db_file


# Import after patching so DB_PATH is already set
import tools.db as db


# ---------------------------------------------------------------------------
# ensure_user
# ---------------------------------------------------------------------------

def test_ensure_user_creates_user():
    db.ensure_user(1001, "Alice")
    goals = db.get_goals(1001)
    assert goals["daily_kcal"] == 2000.0
    assert goals["daily_protein_g"] == 150.0


def test_ensure_user_is_idempotent():
    """Calling ensure_user twice should not raise or duplicate."""
    db.ensure_user(1001, "Alice")
    db.ensure_user(1001, "Alice Updated")
    # Should still work and not throw
    goals = db.get_goals(1001)
    assert goals is not None


def test_ensure_user_creates_default_goals():
    db.ensure_user(1002, "Bob")
    goals = db.get_goals(1002)
    assert goals["daily_kcal"] == 2000.0
    assert goals["daily_protein_g"] == 150.0


# ---------------------------------------------------------------------------
# set_goals / get_goals
# ---------------------------------------------------------------------------

def test_set_goals_updates_correctly():
    db.ensure_user(1001, "Alice")
    db.set_goals(1001, 2500.0, 180.0)
    goals = db.get_goals(1001)
    assert goals["daily_kcal"] == 2500.0
    assert goals["daily_protein_g"] == 180.0


def test_get_goals_returns_defaults_for_unknown_user():
    """User with no goals row should return defaults, not crash."""
    goals = db.get_goals(9999)
    assert goals["daily_kcal"] == 2000.0
    assert goals["daily_protein_g"] == 150.0


def test_set_goals_upserts_not_duplicates():
    """Setting goals twice should update, not create two rows."""
    db.ensure_user(1001, "Alice")
    db.set_goals(1001, 2000.0, 150.0)
    db.set_goals(1001, 2500.0, 180.0)
    goals = db.get_goals(1001)
    assert goals["daily_kcal"] == 2500.0


# ---------------------------------------------------------------------------
# save_meal
# ---------------------------------------------------------------------------

SAMPLE_ITEMS = [
    {
        "name": "chicken breast",
        "grams": 150,
        "kcal_per_100g": 165.0,
        "protein_g": 31.0,
        "fat_g": 3.6,
        "carbs_g": 0.0,
        "confidence": 0.9,
    },
    {
        "name": "brown rice",
        "grams": 180,
        "kcal_per_100g": 130.0,
        "protein_g": 2.7,
        "fat_g": 1.0,
        "carbs_g": 28.0,
        "confidence": 0.85,
    },
]


def test_save_meal_returns_id():
    db.ensure_user(1001, "Alice")
    meal_id = db.save_meal(1001, "downloads/test.jpg", "Test meal", SAMPLE_ITEMS)
    assert isinstance(meal_id, int)
    assert meal_id > 0


def test_save_meal_calculates_totals_correctly():
    db.ensure_user(1001, "Alice")
    db.save_meal(1001, None, "Test meal", SAMPLE_ITEMS)

    summary = db.get_today_summary(1001)
    # chicken: 165 * 1.5 = 247.5, rice: 130 * 1.8 = 234.0 → total 481.5
    assert abs(summary["total_kcal"] - 481.5) < 1.0
    # chicken protein: 31 * 1.5 = 46.5, rice: 2.7 * 1.8 = 4.86 → 51.36
    assert abs(summary["total_protein_g"] - 51.36) < 1.0


def test_save_meal_with_no_items():
    """Empty items list should save without crashing, totals all zero."""
    db.ensure_user(1001, "Alice")
    meal_id = db.save_meal(1001, None, "Empty meal", [])
    assert meal_id > 0
    summary = db.get_today_summary(1001)
    assert summary["total_kcal"] == 0.0


def test_save_meal_with_missing_nutrition_fields():
    """Items with missing nutrition fields should default to 0, not crash."""
    db.ensure_user(1001, "Alice")
    items = [{"name": "mystery food", "grams": 100}]
    meal_id = db.save_meal(1001, None, "Mystery meal", items)
    assert meal_id > 0


def test_save_multiple_meals_accumulates():
    db.ensure_user(1001, "Alice")
    db.save_meal(1001, None, "Meal 1", SAMPLE_ITEMS)
    db.save_meal(1001, None, "Meal 2", SAMPLE_ITEMS)
    summary = db.get_today_summary(1001)
    assert summary["meals_count"] == 2
    assert abs(summary["total_kcal"] - 963.0) < 2.0  # 481.5 * 2


# ---------------------------------------------------------------------------
# get_today_summary
# ---------------------------------------------------------------------------

def test_get_today_summary_no_meals():
    db.ensure_user(1001, "Alice")
    summary = db.get_today_summary(1001)
    assert summary["meals_count"] == 0
    assert summary["total_kcal"] == 0.0
    assert summary["daily_kcal"] == 2000.0
    assert summary["kcal_remaining"] == 2000.0


def test_get_today_summary_goal_progress():
    db.ensure_user(1001, "Alice")
    db.set_goals(1001, 2000.0, 150.0)
    db.save_meal(1001, None, "Meal", SAMPLE_ITEMS)

    summary = db.get_today_summary(1001)
    assert summary["kcal_remaining"] == max(0.0, 2000.0 - summary["total_kcal"])
    assert summary["protein_remaining"] == max(0.0, 150.0 - summary["total_protein_g"])


def test_get_today_summary_remaining_never_negative():
    """kcal_remaining and protein_remaining should never go below 0."""
    db.ensure_user(1001, "Alice")
    db.set_goals(1001, 100.0, 10.0)  # very low goals
    db.save_meal(1001, None, "Big meal", SAMPLE_ITEMS)  # 481 kcal > 100 goal

    summary = db.get_today_summary(1001)
    assert summary["kcal_remaining"] == 0.0
    assert summary["protein_remaining"] == 0.0


# ---------------------------------------------------------------------------
# get_meal_history
# ---------------------------------------------------------------------------

def test_get_meal_history_empty():
    db.ensure_user(1001, "Alice")
    history = db.get_meal_history(1001)
    assert history == []


def test_get_meal_history_returns_correct_count():
    db.ensure_user(1001, "Alice")
    for i in range(5):
        db.save_meal(1001, None, f"Meal {i}", SAMPLE_ITEMS)

    history = db.get_meal_history(1001, limit=3)
    assert len(history) == 3


def test_get_meal_history_most_recent_first():
    db.ensure_user(1001, "Alice")
    db.save_meal(1001, None, "First meal", SAMPLE_ITEMS)
    db.save_meal(1001, None, "Second meal", SAMPLE_ITEMS)

    history = db.get_meal_history(1001)
    assert history[0]["summary"] == "Second meal"
    assert history[1]["summary"] == "First meal"


def test_get_meal_history_contains_expected_keys():
    db.ensure_user(1001, "Alice")
    db.save_meal(1001, None, "Test meal", SAMPLE_ITEMS)

    history = db.get_meal_history(1001)
    assert len(history) == 1
    meal = history[0]
    assert "timestamp" in meal
    assert "summary" in meal
    assert "total_kcal" in meal
    assert "total_protein_g" in meal


# ---------------------------------------------------------------------------
# get_week_summary
# ---------------------------------------------------------------------------

def test_get_week_summary_empty():
    db.ensure_user(1001, "Alice")
    week = db.get_week_summary(1001)
    assert week == []


def test_get_week_summary_includes_today():
    db.ensure_user(1001, "Alice")
    db.save_meal(1001, None, "Today meal", SAMPLE_ITEMS)

    week = db.get_week_summary(1001)
    assert len(week) == 1
    assert week[0]["meals_count"] == 1


def test_get_week_summary_contains_expected_keys():
    db.ensure_user(1001, "Alice")
    db.save_meal(1001, None, "Meal", SAMPLE_ITEMS)

    week = db.get_week_summary(1001)
    day = week[0]
    assert "date" in day
    assert "meals_count" in day
    assert "total_kcal" in day
    assert "total_protein_g" in day


# ---------------------------------------------------------------------------
# get_all_user_ids
# ---------------------------------------------------------------------------

def test_get_all_user_ids_empty():
    ids = db.get_all_user_ids()
    assert ids == []


def test_get_all_user_ids_returns_all():
    db.ensure_user(1001, "Alice")
    db.ensure_user(1002, "Bob")
    db.ensure_user(1003, "Carol")

    ids = db.get_all_user_ids()
    assert set(ids) == {1001, 1002, 1003}


def test_get_all_user_ids_no_duplicates():
    db.ensure_user(1001, "Alice")
    db.ensure_user(1001, "Alice Again")  # same user, should not duplicate

    ids = db.get_all_user_ids()
    assert ids.count(1001) == 1