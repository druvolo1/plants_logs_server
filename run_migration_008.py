"""
Migration 008: Add device debug logs table
- Creates device_debug_logs table for storing debug log metadata
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

            # Create device_debug_logs table
            print("\nCreating device_debug_logs table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_debug_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    device_id INT NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    requested_duration INT NOT NULL,
                    actual_duration INT NULL,
                    file_size INT NULL,
                    early_cutoff_reason VARCHAR(255) NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at DATETIME NULL,
                    completed_at DATETIME NULL,
                    requested_by_user_id INT NULL,
                    CONSTRAINT fk_debug_logs_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                    CONSTRAINT fk_debug_logs_user FOREIGN KEY (requested_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
                    INDEX idx_device_debug_logs_device_id (device_id),
                    INDEX idx_device_debug_logs_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            print("✓ device_debug_logs table created")

            connection.commit()
            print("\n✓ Migration 008 completed successfully!")
            print("\nChanges made:")
            print("- Created device_debug_logs table")

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
    print("Running Migration 008: Add Device Debug Logs Table")
    print("=" * 60)
    run_migration()
