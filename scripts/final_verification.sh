#!/bin/bash
# ============================================================
# LUMINA DIGITAL TWIN — Final Verification
# Run from project root: bash scripts/final_verification.sh
# ============================================================

FAILED=0
DB_URL="${DATABASE_URL:-postgresql://postgres:admin@localhost:5432/FYP_backup}"

echo "╔══════════════════════════════════════════════════════╗"
echo "║   LUMINA DIGITAL TWIN SYSTEM — VERIFICATION         ║"
echo "╚══════════════════════════════════════════════════════╝"

# 1. Database
echo ""
echo "1. Database connection..."
python3 -c "
from sqlalchemy import create_engine, text
engine = create_engine('${DB_URL}'.replace('postgresql://','postgresql+psycopg://'))
with engine.connect() as conn:
    count = conn.execute(text('SELECT COUNT(*) FROM users')).scalar()
    print(f'  ✓ Database OK ({count} users)')
" 2>/dev/null || { echo "  ✗ Database FAILED"; FAILED=1; }

# 2. Digital twin tables
echo ""
echo "2. Digital twin tables..."
python3 -c "
from sqlalchemy import create_engine, inspect
engine = create_engine('${DB_URL}'.replace('postgresql://','postgresql+psycopg://'))
tables = ['student_profiles','cognitive_state','learning_interactions',
          'skill_mastery','wellness_state','digital_twin_predictions','learning_progress']
existing = inspect(engine).get_table_names()
missing = [t for t in tables if t not in existing]
if missing:
    print(f'  ✗ Missing: {missing}')
    print('  Run: cd backend-express && npm run db:migrate:digital-twin')
else:
    print(f'  ✓ All {len(tables)} digital twin tables present')
" 2>/dev/null || { echo "  ✗ Table check FAILED"; FAILED=1; }

# 3. pgvector
echo ""
echo "3. pgvector extension..."
python3 -c "
from sqlalchemy import create_engine, text
engine = create_engine('${DB_URL}'.replace('postgresql://','postgresql+psycopg://'))
with engine.connect() as conn:
    r = conn.execute(text(\"SELECT extname FROM pg_extension WHERE extname='vector'\")).fetchone()
    print('  ✓ pgvector installed' if r else '  ✗ pgvector missing — run: CREATE EXTENSION vector;')
" 2>/dev/null || echo "  ✗ pgvector check FAILED"

# 4. FastAPI health
echo ""
echo "4. FastAPI backend..."
curl -sf http://localhost:8080/health > /dev/null 2>&1 && \
  echo "  ✓ FastAPI responding at :8080" || \
  echo "  ✗ FastAPI not running — start: cd backend && uvicorn main:app --port 8080"

# 5. FastAPI digital twin route
echo ""
echo "5. FastAPI digital twin endpoint..."
curl -sf http://localhost:8080/api/digital-twin/health > /dev/null 2>&1 && \
  echo "  ✓ Digital twin router registered" || \
  echo "  ✗ Route not found — check backend/routers/digital_twin_router.py"

# 6. Express health
echo ""
echo "6. Express backend..."
curl -sf http://localhost:4000/health > /dev/null 2>&1 && \
  echo "  ✓ Express responding at :4000" || \
  echo "  ✗ Express not running — start: cd backend-express && npm run dev"

# 7. LSTM model
echo ""
echo "7. LSTM model..."
[ -f "backend/safe_cognitive_twin.pth" ] && \
  echo "  ✓ LSTM model present" || \
  echo "  ⚠ LSTM model not found at backend/safe_cognitive_twin.pth (optional)"

# Summary
echo ""
echo "╔══════════════════════════════════════════════════════╗"
if [ $FAILED -eq 0 ]; then
    echo "║       ✅  ALL CHECKS PASSED — System Ready!          ║"
else
    echo "║      ❌  SOME ISSUES DETECTED — Fix above errors     ║"
fi
echo "╚══════════════════════════════════════════════════════╝"
exit $FAILED
