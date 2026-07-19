"""
Migration: Add user_id column to jobs and web_automations tables.

Fixes:
  - psycopg2.errors.UndefinedColumn: column "user_id" of relation "jobs" does not exist
  - psycopg2.errors.UndefinedColumn: column web_automations.user_id does not exist

These tables were created before user_id was added to the SQLAlchemy models.
SQLAlchemy's create_all() only creates new tables — it never ALTER-s existing ones,
so this migration must be run manually once.

Usage:
    source venv/bin/activate
    python3 migrations/add_user_id_to_jobs.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine


MIGRATIONS = [
    {
        "table": "jobs",
        "column": "user_id",
        "alter": "ALTER TABLE jobs ADD COLUMN user_id VARCHAR",
        "index": "CREATE INDEX IF NOT EXISTS ix_jobs_user_id ON jobs (user_id)",
    },
    {
        "table": "web_automations",
        "column": "user_id",
        "alter": "ALTER TABLE web_automations ADD COLUMN user_id VARCHAR",
        "index": "CREATE INDEX IF NOT EXISTS ix_web_automations_user_id ON web_automations (user_id)",
    },
]


def run():
    with engine.connect() as conn:
        for m in MIGRATIONS:
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table AND column_name = :column
            """), {"table": m["table"], "column": m["column"]})

            if result.fetchone():
                print(f"[SKIP] '{m['column']}' already exists on '{m['table']}'.")
                continue

            print(f"[RUN ] Adding '{m['column']}' to '{m['table']}'...")
            conn.execute(text(m["alter"]))
            conn.execute(text(m["index"]))
            conn.commit()
            print(f"[DONE] '{m['table']}.{m['column']}' added.")

    print("\nAll migrations complete.")


if __name__ == "__main__":
    run()
