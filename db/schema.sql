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

CREATE TABLE IF NOT EXISTS episodes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER REFERENCES users(user_id),
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    summary   TEXT NOT NULL,
    embedding TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_meal_log_user_time
    ON meal_log(user_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_meal_items_meal
    ON meal_items(meal_id);