"""Pytest fixtures for Banco Inter Payment Gateway test suite."""

from pathlib import Path
import aiosqlite
import pytest


@pytest.fixture
async def temp_db(tmp_path: Path):
    """Creates a temporary SQLite database initialized with leads and pix_transactions."""
    db_file = tmp_path / "test_pipeline.db"
    async with aiosqlite.connect(str(db_file)) as db:
        await db.execute(
            """
            CREATE TABLE leads (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                niche TEXT,
                phone TEXT UNIQUE,
                address TEXT,
                rating REAL,
                reviews_count INTEGER,
                instagram_url TEXT,
                extracted_data TEXT,
                stage TEXT NOT NULL DEFAULT 'MINED',
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
                pix_copia_e_cola TEXT,
                qr_code_base64 TEXT,
                created_at TEXT NOT NULL,
                paid_at TEXT
            )
            """
        )
        # Seed a test lead in OUTREACH stage
        await db.execute(
            """
            INSERT INTO leads (id, name, stage, created_at, updated_at)
            VALUES ('barbearia-vintage', 'Barbearia Vintage', 'OUTREACH', '2026-11-13T12:00:00Z', '2026-11-13T12:00:00Z')
            """
        )
        await db.commit()
    return str(db_file)
