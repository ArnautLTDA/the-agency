"""Pytest fixtures for Cloud Deploy Gateway test suite."""

from pathlib import Path
import aiosqlite
import pytest


@pytest.fixture
async def temp_db(tmp_path: Path):
    """Creates a temporary SQLite database initialized with all tables needed for Triple Gate."""
    db_file = tmp_path / "test_pipeline.db"
    async with aiosqlite.connect(str(db_file)) as db:
        await db.execute(
            """
            CREATE TABLE leads (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                stage TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE pix_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txid TEXT UNIQUE NOT NULL,
                lead_id TEXT,
                amount_cents INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                paid_at TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id TEXT,
                workspace_id TEXT,
                deployment_type TEXT,
                deployment_url TEXT,
                status TEXT,
                qa_approved INTEGER DEFAULT 0,
                security_approved INTEGER DEFAULT 0,
                payment_cleared INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE security_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id TEXT,
                workspace_id TEXT,
                scan_type TEXT,
                status TEXT NOT NULL,
                critical_count INTEGER DEFAULT 0,
                high_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.commit()
    return str(db_file)
