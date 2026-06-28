# db/init_db.py
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("data/meals.db")


def init_db() -> None:
    """Create DB file and tables from schema.sql. Call once at bot startup."""
    DB_PATH.parent.mkdir(exist_ok=True)
    schema = Path("db/schema.sql").read_text()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema)
    conn.commit()
    conn.close()
    logger.info("Database ready at %s", DB_PATH)