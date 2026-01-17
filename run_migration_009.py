"""
Migration 009: Add social media features
- Creates grower_profiles table
- Creates product_locations table
- Creates published_reports table
- Creates upcoming_strains table
- Creates strain_reviews table
- Creates review_responses table
- Creates admin_settings table
"""

import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()

def run_migration():
    connection = None
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

            # Read and execute migration SQL file
            print("\nReading migration SQL file...")
            with open('migrations/009_add_social_media_features.sql', 'r') as f:
                sql_script = f.read()

            print("\nExecuting migration SQL...")
            # Split by semicolon and execute each statement
            statements = sql_script.split(';')
            for statement in statements:
                statement = statement.strip()
                if statement and not statement.startswith('--'):
                    cursor.execute(statement)

            connection.commit()
            print("\n✓ Migration 009 completed successfully!")
            print("\nChanges made:")
            print("- Created grower_profiles table")
            print("- Created product_locations table")
            print("- Created published_reports table")
            print("- Created upcoming_strains table")
            print("- Created strain_reviews table")
            print("- Created review_responses table")
            print("- Created admin_settings table")
            print("- Inserted default admin settings")

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
    print("Running Migration 009: Add Social Media Features")
    print("=" * 60)
    run_migration()
