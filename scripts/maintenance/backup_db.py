#!/usr/bin/env python3
"""Hot SQLite WAL Backup and 7-Day Retention Script (TC-223, TC-224)."""

import gzip
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from datetime import datetime, timezone, timedelta


def run_backup(
    db_file: str = "services/engine/pipeline.db",
    backup_dir: str = "storage/backups/sqlite",
    retention_days: int = 7,
) -> Path:
    db_path = Path(db_file)
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise FileNotFoundError(f"Database file '{db_path}' not found.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = target_dir / f"pipeline-{timestamp}.db"

    # 1. Hot atomic backup using VACUUM INTO
    print(f"Initiating atomic hot backup of '{db_path}' using VACUUM INTO...")
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(f"VACUUM INTO '{backup_path}';")
    finally:
        conn.close()

    # 2. Integrity check on snapshot
    print(f"Validating backup database integrity on '{backup_path}'...")
    check_conn = sqlite3.connect(str(backup_path))
    try:
        cur = check_conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        result = cur.fetchone()[0]
        if result != "ok":
            if backup_path.exists():
                backup_path.unlink()
            raise RuntimeError(f"Integrity check failed: {result}")
    finally:
        check_conn.close()

    # 3. Compress snapshot
    gz_path = target_dir / f"{backup_path.name}.gz"
    print(f"Compressing backup snapshot to '{gz_path}'...")
    with open(backup_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    backup_path.unlink()
    print(f"Backup successfully created and verified: {gz_path}")

    # 4. Retention policy: expunge files older than retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    for entry in target_dir.glob("pipeline-*.db.gz"):
        file_mtime = datetime.fromtimestamp(entry.stat().st_mtime, timezone.utc)
        if file_mtime < cutoff:
            print(f"Expunging old backup snapshot: {entry.name}")
            entry.unlink()

    return gz_path


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "services/engine/pipeline.db"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "storage/backups/sqlite"
    retention = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    run_backup(db, out_dir, retention)
