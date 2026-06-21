#!/usr/bin/env python3
"""
Process ASSISTments parquet files to create initial digital twins.

Usage:
    cd backend
    python scripts/process_assistments_data.py /path/to/clean_assistments_data/
"""

import sys
from pathlib import Path

# Make sure backend/ is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from db import SessionLocal
from services.digital_twin_factory import AssistmentsDigitalTwinPipeline


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/process_assistments_data.py /path/to/data/")
        sys.exit(1)

    input_folder = sys.argv[1]

    print("=" * 70)
    print("Processing ASSISTments Data → Digital Twins")
    print("=" * 70)

    db = SessionLocal()
    pipeline = AssistmentsDigitalTwinPipeline(
        db_session=db,
        lstm_model_path=str(Path(__file__).parent.parent / "safe_cognitive_twin.pth"),
    )

    results = pipeline.process_all_assistments_files(
        input_folder=input_folder,
        output_log="failed_students.csv",
    )

    print("\n" + "=" * 70)
    print(f"✓ Created:  {results['total_created']}")
    print(f"✗ Failed:   {results['total_failed']}")
    print(f"  Rate:     {results['success_rate']:.1%}")
    print("=" * 70)

    db.close()


if __name__ == "__main__":
    main()
