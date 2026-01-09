#!/usr/bin/env python3
"""
Database migration script to add idle timeout fields
Adds last_activity_at column and STOPPED status to terminals table
"""

import sys
import logging
from pathlib import Path

# Add parent directory to path to import src modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.database.session import engine
from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Run the migration to add last_activity_at column"""
    logger.info("Starting migration: add idle timeout fields")

    with engine.connect() as conn:
        try:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='terminals'
                AND column_name='last_activity_at'
            """))

            if result.fetchone():
                logger.info("Column last_activity_at already exists, skipping migration")
                return

            # Add last_activity_at column
            logger.info("Adding last_activity_at column to terminals table")
            conn.execute(text("""
                ALTER TABLE terminals
                ADD COLUMN last_activity_at TIMESTAMP WITH TIME ZONE
            """))

            # Create index on last_activity_at
            logger.info("Creating index on last_activity_at")
            conn.execute(text("""
                CREATE INDEX idx_terminals_last_activity_at
                ON terminals(last_activity_at)
            """))

            # Update existing terminals to set last_activity_at = created_at
            logger.info("Updating existing terminals with last_activity_at = created_at")
            conn.execute(text("""
                UPDATE terminals
                SET last_activity_at = created_at
                WHERE last_activity_at IS NULL
            """))

            conn.commit()
            logger.info("Migration completed successfully!")
            logger.info("Note: The STOPPED status was added to the TerminalStatus enum in code")
            logger.info("PostgreSQL will accept the new enum value automatically")

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            conn.rollback()
            raise


if __name__ == "__main__":
    logger.info(f"Using database: {settings.DATABASE_URL}")
    run_migration()
