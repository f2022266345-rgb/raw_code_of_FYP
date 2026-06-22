"""
backend/scripts/run_migrations.py
─────────────────────────────────
One command to bring a database fully up to date for the FastAPI side:

  1. Ensure the pgvector extension exists.
  2. Create all ORM tables (init_db / create_all) — safe if they already exist.
  3. Apply every backend/migrations/*.sql in filename order. These add the
     DB-level column DEFAULTs that raw INSERTs rely on (fixes the recurring
     NotNullViolation on created_at / state_confidence / p_init / ...).

All steps are idempotent, so this is safe to run on every deploy.

Usage:
  cd backend
  python scripts/run_migrations.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the backend package importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()


def _normalized_url() -> str:
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:admin@localhost:5432/FYP_DB_Latest")
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def main() -> int:
    from sqlalchemy import create_engine

    url = _normalized_url()
    target = url.rsplit("@", 1)[-1]
    print(f"[migrations] target DB: {target}")

    eng = create_engine(url, future=True)

    # 1. pgvector
    with eng.begin() as conn:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    print("[migrations] pgvector ensured")

    # 2. ORM tables
    try:
        from db import init_db
        init_db()
        print("[migrations] ORM tables ensured (create_all)")
    except Exception as exc:  # non-fatal: tables may be owned elsewhere
        print(f"[migrations] init_db warning (non-fatal): {exc}")

    # 3. SQL migrations in order
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        print("[migrations] no .sql files found")
    for f in sql_files:
        try:
            with eng.begin() as conn:
                conn.exec_driver_sql(f.read_text(encoding="utf-8"))
            print(f"[migrations] applied {f.name}")
        except Exception as exc:
            # 002/003 create tables that may already exist with FKs to users; keep going.
            print(f"[migrations] skipped {f.name} ({type(exc).__name__}: {str(exc)[:120]})")

    print("[migrations] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
