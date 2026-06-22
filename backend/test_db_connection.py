#!/usr/bin/env python3
"""
Test database connection and verify all digital twin tables exist.
Run: python test_db_connection.py
"""

import os
import sys

from sqlalchemy import create_engine, inspect, text


def _normalize(url: str) -> str:
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DB_URL = _normalize(
    os.getenv("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/FYP_DB_Latest")
)

print("=" * 60)
print("Digital Twin — Database Connection Test")
print("=" * 60)

print("\n1. Connecting...")
try:
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("   ✓ Connected")
except Exception as exc:
    print(f"   ✗ Connection failed: {exc}")
    sys.exit(1)

print("\n2. Checking pgvector...")
try:
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).fetchone()
        if result:
            print("   ✓ pgvector installed")
        else:
            print("   ✗ pgvector NOT installed — run: CREATE EXTENSION vector;")
except Exception as exc:
    print(f"   ✗ {exc}")

print("\n3. Verifying digital twin tables...")
required = [
    "users",
    "student_profiles",
    "cognitive_state",
    "learning_interactions",
    "skill_mastery",
    "wellness_state",
    "digital_twin_predictions",
    "learning_progress",
]
inspector = inspect(engine)
existing = inspector.get_table_names()
missing = [t for t in required if t not in existing]

if missing:
    print(f"   ✗ Missing tables: {missing}")
    print("\n   Run the migration:")
    print("   psql -U postgres -d YOUR_DB -f backend/migrations/002_digital_twin_tables.sql")
    print("   OR from backend-express: npm run db:migrate:digital-twin")
else:
    print(f"   ✓ All {len(required)} tables present")

print("\n4. Row counts...")
with engine.connect() as conn:
    for table in required:
        if table in existing:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"   {table}: {count} rows")

print("\n5. Testing vector ops...")
try:
    with engine.connect() as conn:
        d = conn.execute(text("SELECT '1 2 3'::vector <-> '1 2 3'::vector")).scalar()
        print(f"   ✓ Vector distance (should be 0): {d}")
except Exception as exc:
    print(f"   ✗ Vector test failed: {exc}")

print("\n" + "=" * 60)
if not missing:
    print("✅ All checks passed — database is ready!")
else:
    print("⚠️  Some tables missing — run migration first.")
print("=" * 60)
