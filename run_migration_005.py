#!/usr/bin/env python3
"""
Run Migration 005: Add curing phase support
"""
import os
import pymysql
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    print("=" * 80)
    print("Running Migration 005: Add curing phase support")
    print("=" * 80)
    print()

    # Database connection details
    db_config = {
        'host': '172.16.1.150',
        'port': 3306,
        'user': 'app_user',
        'password': 'testpass123',
        'database': 'plant_logs_dev'
    }

    print(f"Connecting to {db_config['database']} on {db_config['host']}...")

    try:
        connection = pymysql.connect(**db_config)
        cursor = connection.cursor()

        print("✓ Connected successfully\n")

        # Read the migration SQL file
        migration_file = 'migrations/005_add_curing_phase.sql'

        with open(migration_file, 'r') as f:
            sql_script = f.read()

        # Split by statement and execute
        statements = []
        current_statement = []

        for line in sql_script.split('\n'):
            # Skip comments and empty lines
            line = line.strip()
            if line.startswith('--') or not line:
                continue

            current_statement.append(line)

            # Check if statement is complete (ends with semicolon)
            if line.endswith(';'):
                stmt = ' '.join(current_statement)
                statements.append(stmt)
                current_statement = []

        print(f"Executing {len(statements)} SQL statements...\n")

        # Execute each statement
        for i, stmt in enumerate(statements, 1):
            try:
                print(f"Statement {i}/{len(statements)}: {stmt[:60]}...")
                cursor.execute(stmt)
                print(f"  ✓ Success")

            except Exception as e:
                # Column already exists is OK
                if 'duplicate column' in str(e).lower() or '1060' in str(e):
                    print(f"  ⚠ Column already exists (skipping)")
                else:
                    print(f"  ✗ Error: {e}")
                    raise

        # Commit all changes
        connection.commit()
        print()

        # Show final plants table schema (relevant columns)
        print("Plants table - expected phase duration columns:")
        cursor.execute("DESCRIBE plants")
        results = cursor.fetchall()

        print(f"\n{'Field':<30} {'Type':<20} {'Null':<6}")
        print("-" * 60)
        for row in results:
            field, type_, null, key, default, extra = row
            if 'expected' in field and 'days' in field:
                print(f"{field:<30} {type_:<20} {null:<6}")

        print()

        # Show phase_templates table schema (relevant columns)
        print("Phase templates table - expected phase duration columns:")
        cursor.execute("DESCRIBE phase_templates")
        results = cursor.fetchall()

        print(f"\n{'Field':<30} {'Type':<20} {'Null':<6}")
        print("-" * 60)
        for row in results:
            field, type_, null, key, default, extra = row
            if 'expected' in field and 'days' in field:
                print(f"{field:<30} {type_:<20} {null:<6}")

        cursor.close()
        connection.close()

        print("\n" + "=" * 80)
        print("✓ Migration 005 completed successfully!")
        print("=" * 80)
        print()
        print("Next steps:")
        print("  1. Restart your FastAPI server")
        print("  2. Test creating/editing templates with curing days")
        print("  3. Test changing plants to curing phase")
        print("  4. Check the new phase timeline tables in the UI")

        return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(run_migration())
