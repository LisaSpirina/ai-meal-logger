-- db/schema.sql

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    first_name TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id),
    daily_kcal INTEGER,
    daily_protein_g INTEGER
);

CREATE TABLE IF NOT EXISTS meal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(user_id),
    timestamp TEXT NOT NULL,
    food_items TEXT NOT NULL,
    total_kcal REAL,
    total_protein_g REAL,
    total_fat_g REAL,
    total_carbs_g REAL
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(user_id),
    timestamp TEXT NOT NULL,
    summary TEXT NOT NULL,
    embedding TEXT NOT NULL
);