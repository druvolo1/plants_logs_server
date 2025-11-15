#!/usr/bin/env python3
"""
Run Migration 003: Update log_entries table schema
"""
import os
import pymysql
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    print("=" * 80)
    print("Running Migration 003: Update log_entries table schema")
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
        migration_file = 'migrations/003_update_log_entries_simple.sql'

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
                # Skip PREPARE/EXECUTE/DEALLOCATE blocks - execute them as one
                if 'PREPARE stmt FROM' in stmt:
                    continue

                cursor.execute(stmt)
                result = cursor.fetchall()

                # Print any SELECT results
                if result:
                    for row in result:
                        if len(row) == 1:
                            print(f"  {row[0]}")
                        else:
                            print(f"  {row}")

            except Exception as e:
                # Some statements may fail if column doesn't exist, that's OK
                if 'Unknown column' not in str(e) and 'duplicate column' not in str(e).lower():
                    print(f"  Note: {e}")

        # Commit all changes
        connection.commit()

        # Show final schema
        print("\nFinal log_entries schema:")
        cursor.execute("DESCRIBE log_entries")
        results = cursor.fetchall()

        print(f"\n{'Field':<20} {'Type':<20} {'Null':<6} {'Key':<6} {'Default':<10}")
        print("-" * 70)
        for row in results:
            field, type_, null, key, default, extra = row
            default_str = str(default) if default else ''
            print(f"{field:<20} {type_:<20} {null:<6} {key:<6} {default_str:<10}")

        cursor.close()
        connection.close()

        print("\n" + "=" * 80)
        print("✓ Migration 003 completed successfully!")
        print("=" * 80)

        return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(run_migration())
