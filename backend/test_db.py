import os
import sys

# Add the current directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from db import engine, text

def check_db():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();")).scalar()
            print(f"Connected to DB successfully. Postgres version: {result}")
            
            # Check for pgvector
            ext_result = conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector';")).scalar()
            if ext_result:
                print("pgvector extension is installed and available.")
            else:
                print("pgvector extension is NOT installed in this database.")
    except Exception as e:
        print(f"Failed to connect to the database or verify pgvector: {e}")

if __name__ == '__main__':
    check_db()
