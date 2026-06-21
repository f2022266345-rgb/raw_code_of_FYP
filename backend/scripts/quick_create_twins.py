#!/usr/bin/env python3
"""
Quick script to create digital twins from ASSISTments data.
Run this ONCE after the database migration.

Usage:
    cd backend
    python scripts/quick_create_twins.py /path/to/clean_assistments_data/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import SessionLocal
from services.digital_twin_factory import DigitalTwinFactory, AssistmentsDigitalTwinPipeline
from sqlalchemy import text

MODEL_PATH = str(Path(__file__).parent.parent / "safe_cognitive_twin.pth")


def main():
    print("=" * 60)
    print("CREATING DIGITAL TWINS FROM ASSISTMENTS DATA")
    print("=" * 60)

    if len(sys.argv) < 2:
        print("Usage: python scripts/quick_create_twins.py /path/to/data/")
        sys.exit(1)

    input_folder = sys.argv[1]

    db = SessionLocal()
    pipeline = AssistmentsDigitalTwinPipeline(
        db_session=db,
        lstm_model_path=MODEL_PATH,
    )

    print(f"\nSearching for parquet files in: {input_folder}")

    results = pipeline.process_all_assistments_files(
        input_folder=input_folder,
        output_log="failed_students.csv",
    )

    print(f"\n✅ COMPLETE!")
    print(f"   Total created: {results['total_created']}")
    print(f"   Total failed:  {results['total_failed']}")
    print(f"   Success rate:  {results['success_rate']:.1%}")

    count = db.execute(
        text("SELECT COUNT(*) FROM digital_twin_predictions")
    ).scalar()
    print(f"\n📊 Database: {count} digital twin predictions stored")

    db.close()


if __name__ == "__main__":
    main()
