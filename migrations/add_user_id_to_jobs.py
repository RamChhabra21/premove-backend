"""
Migration: Add user_id column to jobs table
Run this once to fix: psycopg2.errors.UndefinedColumn: column "user_id" of relation "jobs" does not exist

Usage:
    python migrations/add_user_id_to_jobs.py
"""

import sys
import os

# Make sure the app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine


def run():
    with engine.connect() as conn:
        # Check if the column already exists to make this idempotent
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'jobs' AND column_name = 'user_id'
        """))
        if result.fetchone():
            print("Column 'user_id' already exists on 'jobs' — nothing to do.")
            return

        print("Adding column 'user_id' (VARCHAR, nullable, indexed) to 'jobs'...")
        conn.execute(text("ALTER TABLE jobs ADD COLUMN user_id VARCHAR"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_user_id ON jobs (user_id)"))
        conn.commit()
        print("Migration complete.")


if __name__ == "__main__":
    run()
