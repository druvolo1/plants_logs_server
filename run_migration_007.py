"""
Migration 007: Add environment sensor support
- Creates environment_logs table
- Adds settings column to devices table
"""

import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()

def run_migration():
    try:
        # Get database connection details from environment
        db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'database': os.getenv('DB_NAME')
        }

        print(f"Connecting to database: {db_config['host']}/{db_config['database']}")
        connection = mysql.connector.connect(**db_config)

        if connection.is_connected():
            cursor = connection.cursor()
            print("✓ Connected to MySQL database")

            # Read migration SQL file
            migration_file = 'migrations/007_add_environment_sensors.sql'
            print(f"\nReading migration file: {migration_file}")

            with open(migration_file, 'r') as f:
                sql_content = f.read()

            # Split into individual statements
            statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip() and not stmt.strip().startswith('--')]

            print(f"Found {len(statements)} SQL statements to execute\n")

            # Execute each statement
            for i, statement in enumerate(statements, 1):
                try:
                    print(f"Executing statement {i}/{len(statements)}...")
                    cursor.execute(statement)
                    print(f"✓ Statement {i} completed successfully")
                except Error as e:
                    # Check if error is about column/table already existing
                    if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                        print(f"⚠ Statement {i} skipped (already exists): {e}")
                    else:
                        print(f"✗ Error in statement {i}: {e}")
                        raise

            connection.commit()
            print("\n✓ Migration 007 completed successfully!")
            print("\nChanges made:")
            print("- Created environment_logs table")
            print("- Added settings column to devices table")

    except Error as e:
        print(f"\n✗ Migration failed: {e}")
        if connection:
            connection.rollback()
        raise

    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()
            print("\nDatabase connection closed")

if __name__ == "__main__":
    print("=" * 60)
    print("Running Migration 007: Add Environment Sensor Support")
    print("=" * 60)
    run_migration()
