#!/usr/bin/env python3
"""
Run Migration 006: Add locations support with arbitrary nesting
"""
import os
import pymysql
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    print("=" * 80)
    print("Running Migration 006: Add locations support")
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
        migration_file = 'migrations/006_add_locations.sql'

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
                # Table/column already exists is OK
                if 'already exists' in str(e).lower() or 'duplicate column' in str(e).lower() or '1050' in str(e) or '1060' in str(e):
                    print(f"  ⚠ Already exists (skipping)")
                else:
                    print(f"  ✗ Error: {e}")
                    raise

        # Commit all changes
        connection.commit()
        print()

        # Show locations table schema
        print("Locations table schema:")
        cursor.execute("DESCRIBE locations")
        results = cursor.fetchall()

        print(f"\n{'Field':<25} {'Type':<20} {'Null':<6} {'Key':<6}")
        print("-" * 70)
        for row in results:
            field, type_, null, key, default, extra = row
            print(f"{field:<25} {type_:<20} {null:<6} {key:<6}")

        print()

        # Show location_shares table schema
        print("Location_shares table schema:")
        cursor.execute("DESCRIBE location_shares")
        results = cursor.fetchall()

        print(f"\n{'Field':<25} {'Type':<20} {'Null':<6} {'Key':<6}")
        print("-" * 70)
        for row in results:
            field, type_, null, key, default, extra = row
            print(f"{field:<25} {type_:<20} {null:<6} {key:<6}")

        print()

        # Verify devices and plants have location_id
        print("Devices table - location_id column:")
        cursor.execute("SHOW COLUMNS FROM devices LIKE 'location_id'")
        result = cursor.fetchone()
        if result:
            print(f"  ✓ location_id column exists: {result[1]}")
        else:
            print(f"  ✗ location_id column NOT found")

        print("\nPlants table - location_id column:")
        cursor.execute("SHOW COLUMNS FROM plants LIKE 'location_id'")
        result = cursor.fetchone()
        if result:
            print(f"  ✓ location_id column exists: {result[1]}")
        else:
            print(f"  ✗ location_id column NOT found")

        cursor.close()
        connection.close()

        print("\n" + "=" * 80)
        print("✓ Migration 006 completed successfully!")
        print("=" * 80)
        print()
        print("Next steps:")
        print("  1. Restart your FastAPI server")
        print("  2. Test creating locations via the API")
        print("  3. Test assigning devices and plants to locations")
        print("  4. Test location sharing functionality")
        print("  5. Test location filtering on the dashboard")

        return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(run_migration())
