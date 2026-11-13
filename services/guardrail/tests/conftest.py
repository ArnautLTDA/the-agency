"""Pytest fixtures for Guardrail Gateway test suite."""

from pathlib import Path
import aiosqlite
import pytest


@pytest.fixture
async def temp_db(tmp_path: Path):
    """Creates a temporary SQLite database initialized with security_incidents table."""
    db_file = tmp_path / "test_pipeline.db"
    async with aiosqlite.connect(str(db_file)) as db:
        await db.execute(
            """
            CREATE TABLE security_incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_jid TEXT NOT NULL,
                raw_message TEXT NOT NULL,
                threat_category TEXT NOT NULL,
                risk_score REAL NOT NULL,
                action_taken TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.commit()
    return str(db_file)
