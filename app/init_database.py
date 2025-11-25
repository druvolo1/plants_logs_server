# app/init_database.py - Database initialization and migration script
"""
This script ensures the database has all required tables and columns.
It runs automatically on application startup and adds any missing schema elements.
"""

from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import create_async_engine
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("mariadb+mariadbconnector", "mariadb+aiomysql")

async def check_and_add_column(connection, table_name: str, column_name: str, column_definition: str):
    """Check if a column exists, and add it if it doesn't."""
    try:
        # Check if column exists
        result = await connection.execute(text(f"""
            SELECT COUNT(*) as count
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table_name}'
            AND COLUMN_NAME = '{column_name}'
        """))
        row = result.fetchone()

        if row[0] == 0:
            # Column doesn't exist, add it
            print(f"  Adding column '{column_name}' to table '{table_name}'...")
            await connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}"))
            # Don't commit here - let the context manager handle it
            print(f"  ✓ Column '{column_name}' added successfully")
            return True
        else:
            print(f"  ✓ Column '{column_name}' already exists in '{table_name}'")
            return False
    except Exception as e:
        print(f"  ✗ Error checking/adding column '{column_name}': {e}")
        return False

async def check_and_modify_column_default(connection, table_name: str, column_name: str, new_default):
    """Modify the default value of a column."""
    try:
        print(f"  Updating default value for '{column_name}' in '{table_name}'...")

        # For MariaDB/MySQL, we need to know the full column definition to modify it
        # Get current column definition
        result = await connection.execute(text(f"""
            SELECT COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table_name}'
            AND COLUMN_NAME = '{column_name}'
        """))
        row = result.fetchone()

        if row:
            column_type = row[0]
            is_nullable = 'NULL' if row[1] == 'YES' else 'NOT NULL'
            current_default = row[2]

            # Check if default needs to be changed
            if str(current_default) != str(new_default):
                # Modify column with new default
                await connection.execute(text(f"""
                    ALTER TABLE {table_name}
                    MODIFY COLUMN {column_name} {column_type} {is_nullable} DEFAULT {new_default}
                """))
                # Don't commit here - let the context manager handle it
                print(f"  ✓ Default value for '{column_name}' updated to {new_default}")
                return True
            else:
                print(f"  ✓ Default value for '{column_name}' is already {new_default}")
                return False
        else:
            print(f"  ✗ Column '{column_name}' not found in '{table_name}'")
            return False

    except Exception as e:
        print(f"  ✗ Error modifying column default: {e}")
        return False

async def check_and_create_table(connection, table_name: str, create_sql: str):
    """Check if a table exists, and create it if it doesn't."""
    try:
        # Check if table exists
        result = await connection.execute(text(f"""
            SELECT COUNT(*) as count
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table_name}'
        """))
        row = result.fetchone()

        if row[0] == 0:
            # Table doesn't exist, create it
            print(f"  Creating table '{table_name}'...")
            await connection.execute(text(create_sql))
            # Don't commit here - let the context manager handle it
            print(f"  ✓ Table '{table_name}' created successfully")
            return True
        else:
            print(f"  ✓ Table '{table_name}' already exists")
            return False
    except Exception as e:
        print(f"  ✗ Error checking/creating table '{table_name}': {e}")
        return False

async def init_database():
    """Initialize database schema with all required tables and columns."""
    print("\n" + "="*80)
    print("DATABASE INITIALIZATION")
    print("="*80)
    
    if not DATABASE_URL:
        print("✗ DATABASE_URL not found in environment variables")
        return False
    
    print(f"Connecting to database...")
    engine = create_async_engine(DATABASE_URL)
    
    try:
        async with engine.begin() as conn:
            print("✓ Connected to database successfully\n")
            
            # Check and create tables if they don't exist
            # Note: FastAPI-Users will create the basic tables, but we need to ensure columns exist
            
            print("Checking 'users' table schema...")
            
            # Add first_name column if it doesn't exist
            await check_and_add_column(
                conn, 
                'users', 
                'first_name', 
                "first_name VARCHAR(255) NULL AFTER email"
            )
            
            # Add last_name column if it doesn't exist
            await check_and_add_column(
                conn,
                'users',
                'last_name',
                "last_name VARCHAR(255) NULL AFTER first_name"
            )

            # Add is_suspended column if it doesn't exist
            await check_and_add_column(
                conn,
                'users',
                'is_suspended',
                "is_suspended BOOLEAN NOT NULL DEFAULT FALSE AFTER is_verified"
            )

            # Add dashboard_preferences column if it doesn't exist
            await check_and_add_column(
                conn,
                'users',
                'dashboard_preferences',
                "dashboard_preferences TEXT NULL AFTER is_suspended"
            )

            # Update is_active default to FALSE for new users (pending approval)
            # Note: This won't affect existing users, only new ones
            await check_and_modify_column_default(
                conn,
                'users',
                'is_active',
                '0'  # FALSE in MySQL/MariaDB
            )

            print("\nChecking 'devices' table schema...")

            # Add scope column if it doesn't exist (plant-level vs room-level)
            await check_and_add_column(
                conn,
                'devices',
                'scope',
                "scope VARCHAR(20) NULL DEFAULT 'plant' AFTER device_type"
            )

            # Add capabilities column if it doesn't exist (JSON field for device capabilities)
            await check_and_add_column(
                conn,
                'devices',
                'capabilities',
                "capabilities TEXT NULL AFTER scope"
            )

            # Add settings column if it doesn't exist (JSON field for device-specific settings)
            await check_and_add_column(
                conn,
                'devices',
                'settings',
                "settings TEXT NULL AFTER capabilities"
            )

            # Add last_seen column if it doesn't exist (better online/offline tracking)
            await check_and_add_column(
                conn,
                'devices',
                'last_seen',
                "last_seen DATETIME NULL AFTER is_online"
            )

            print("\nChecking 'plants' table schema...")

            # Add batch_number column if it doesn't exist
            await check_and_add_column(
                conn,
                'plants',
                'batch_number',
                "batch_number VARCHAR(100) NULL AFTER name"
            )

            # Add display_order column if it doesn't exist
            await check_and_add_column(
                conn,
                'plants',
                'display_order',
                "display_order INT NULL DEFAULT 0 AFTER yield_grams"
            )

            # Add status column if it doesn't exist
            await check_and_add_column(
                conn,
                'plants',
                'status',
                "status VARCHAR(50) NOT NULL DEFAULT 'created' AFTER display_order"
            )

            # Add current_phase column if it doesn't exist
            await check_and_add_column(
                conn,
                'plants',
                'current_phase',
                "current_phase VARCHAR(50) NULL AFTER status"
            )

            # Add harvest_date column if it doesn't exist
            await check_and_add_column(
                conn,
                'plants',
                'harvest_date',
                "harvest_date DATETIME NULL AFTER current_phase"
            )

            # Add cure_start_date column if it doesn't exist
            await check_and_add_column(
                conn,
                'plants',
                'cure_start_date',
                "cure_start_date DATETIME NULL AFTER harvest_date"
            )

            # Add cure_end_date column if it doesn't exist
            await check_and_add_column(
                conn,
                'plants',
                'cure_end_date',
                "cure_end_date DATETIME NULL AFTER cure_start_date"
            )

            # Add expected phase duration columns if they don't exist
            await check_and_add_column(
                conn,
                'plants',
                'expected_seed_days',
                "expected_seed_days INT NULL AFTER cure_end_date"
            )

            await check_and_add_column(
                conn,
                'plants',
                'expected_clone_days',
                "expected_clone_days INT NULL AFTER expected_seed_days"
            )

            await check_and_add_column(
                conn,
                'plants',
                'expected_veg_days',
                "expected_veg_days INT NULL AFTER expected_clone_days"
            )

            await check_and_add_column(
                conn,
                'plants',
                'expected_flower_days',
                "expected_flower_days INT NULL AFTER expected_veg_days"
            )

            await check_and_add_column(
                conn,
                'plants',
                'expected_drying_days',
                "expected_drying_days INT NULL AFTER expected_flower_days"
            )

            await check_and_add_column(
                conn,
                'plants',
                'expected_curing_days',
                "expected_curing_days INT NULL AFTER expected_drying_days"
            )

            await check_and_add_column(
                conn,
                'plants',
                'template_id',
                "template_id INT NULL AFTER expected_curing_days"
            )

            print("\nChecking 'device_shares' table...")

            # Create device_shares table if it doesn't exist
            await check_and_create_table(
                conn,
                'device_shares',
                """
                CREATE TABLE device_shares (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    device_id INT NOT NULL,
                    owner_user_id INT NOT NULL,
                    shared_with_user_id INT NULL,
                    share_code VARCHAR(12) NOT NULL UNIQUE,
                    permission_level VARCHAR(20) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    accepted_at DATETIME NULL,
                    revoked_at DATETIME NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    INDEX idx_device_id (device_id),
                    INDEX idx_share_code (share_code),
                    INDEX idx_owner_user_id (owner_user_id),
                    INDEX idx_shared_with_user_id (shared_with_user_id),
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (shared_with_user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

            print("\nChecking 'locations' table...")

            # Create locations table if it doesn't exist
            await check_and_create_table(
                conn,
                'locations',
                """
                CREATE TABLE locations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT NULL,
                    parent_id INT NULL,
                    user_id INT NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_parent_id (parent_id),
                    INDEX idx_user_id (user_id),
                    FOREIGN KEY (parent_id) REFERENCES locations(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

            print("\nChecking 'location_shares' table...")

            # Create location_shares table if it doesn't exist
            await check_and_create_table(
                conn,
                'location_shares',
                """
                CREATE TABLE location_shares (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    location_id INT NOT NULL,
                    owner_user_id INT NOT NULL,
                    shared_with_user_id INT NULL,
                    share_code VARCHAR(12) NOT NULL UNIQUE,
                    permission_level VARCHAR(20) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    accepted_at DATETIME NULL,
                    revoked_at DATETIME NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    INDEX idx_location_id (location_id),
                    INDEX idx_share_code (share_code),
                    INDEX idx_owner_user_id (owner_user_id),
                    INDEX idx_shared_with_user_id (shared_with_user_id),
                    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE,
                    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (shared_with_user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

            print("\nAdding location_id column to devices and plants tables...")

            # Add location_id to devices table
            await check_and_add_column(
                conn,
                'devices',
                'location_id',
                "location_id INT NULL AFTER user_id"
            )

            # Add foreign key for devices.location_id if it doesn't exist
            try:
                # Check if foreign key exists
                result = await conn.execute(text("""
                    SELECT COUNT(*) as count
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'devices'
                    AND COLUMN_NAME = 'location_id'
                    AND REFERENCED_TABLE_NAME = 'locations'
                """))
                row = result.fetchone()

                if row[0] == 0:
                    print("  Adding foreign key constraint for devices.location_id...")
                    await conn.execute(text("""
                        ALTER TABLE devices
                        ADD CONSTRAINT fk_devices_location
                        FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
                    """))
                    print("  ✓ Foreign key constraint added")
                else:
                    print("  ✓ Foreign key constraint already exists")
            except Exception as e:
                print(f"  Note: Foreign key constraint may already exist or error occurred: {e}")

            # Add location_id to plants table
            await check_and_add_column(
                conn,
                'plants',
                'location_id',
                "location_id INT NULL AFTER user_id"
            )

            # Add foreign key for plants.location_id if it doesn't exist
            try:
                # Check if foreign key exists
                result = await conn.execute(text("""
                    SELECT COUNT(*) as count
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'plants'
                    AND COLUMN_NAME = 'location_id'
                    AND REFERENCED_TABLE_NAME = 'locations'
                """))
                row = result.fetchone()

                if row[0] == 0:
                    print("  Adding foreign key constraint for plants.location_id...")
                    await conn.execute(text("""
                        ALTER TABLE plants
                        ADD CONSTRAINT fk_plants_location
                        FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
                    """))
                    print("  ✓ Foreign key constraint added")
                else:
                    print("  ✓ Foreign key constraint already exists")
            except Exception as e:
                print(f"  Note: Foreign key constraint may already exist or error occurred: {e}")

            print("\nChecking 'log_entries' table schema...")

            # Add device_id column to log_entries table if it doesn't exist
            # This is for the new device-centric logging architecture
            await check_and_add_column(
                conn,
                'log_entries',
                'device_id',
                "device_id INT NULL AFTER id"
            )

            # Add index on device_id for log_entries if column was just added
            try:
                result = await conn.execute(text("""
                    SELECT COUNT(*) as count
                    FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'log_entries'
                    AND INDEX_NAME = 'idx_log_entries_device_id'
                """))
                row = result.fetchone()
                if row[0] == 0:
                    print("  Adding index on log_entries.device_id...")
                    await conn.execute(text("CREATE INDEX idx_log_entries_device_id ON log_entries(device_id)"))
                    print("  ✓ Index added")
                else:
                    print("  ✓ Index on device_id already exists")
            except Exception as e:
                print(f"  Note: Index may already exist: {e}")

            # Add foreign key for log_entries.device_id if it doesn't exist
            try:
                result = await conn.execute(text("""
                    SELECT COUNT(*) as count
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'log_entries'
                    AND COLUMN_NAME = 'device_id'
                    AND REFERENCED_TABLE_NAME = 'devices'
                """))
                row = result.fetchone()
                if row[0] == 0:
                    print("  Adding foreign key constraint for log_entries.device_id...")
                    await conn.execute(text("""
                        ALTER TABLE log_entries
                        ADD CONSTRAINT fk_log_entries_device
                        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                    """))
                    print("  ✓ Foreign key constraint added")
                else:
                    print("  ✓ Foreign key constraint already exists")
            except Exception as e:
                print(f"  Note: Foreign key may already exist or error: {e}")

            # Add created_at column to log_entries if it doesn't exist
            await check_and_add_column(
                conn,
                'log_entries',
                'created_at',
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER timestamp"
            )

            # Make plant_id nullable (for new device-centric logging where plant_id is not required)
            try:
                result = await conn.execute(text("""
                    SELECT IS_NULLABLE
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'log_entries'
                    AND COLUMN_NAME = 'plant_id'
                """))
                row = result.fetchone()
                if row and row[0] == 'NO':
                    print("  Making log_entries.plant_id nullable for device-centric logging...")
                    await conn.execute(text("""
                        ALTER TABLE log_entries
                        MODIFY COLUMN plant_id INT NULL
                    """))
                    print("  ✓ log_entries.plant_id is now nullable")
                elif row:
                    print("  ✓ log_entries.plant_id is already nullable")
                else:
                    print("  Note: plant_id column not found in log_entries")
            except Exception as e:
                print(f"  Note: Error modifying plant_id: {e}")

            print("\nChecking 'device_links' table...")

            # Add removed_at column to device_links table if it doesn't exist
            await check_and_add_column(
                conn,
                'device_links',
                'removed_at',
                "removed_at DATETIME NULL AFTER created_at"
            )

            print("\nChecking 'plant_reports' table...")

            # Create plant_reports table if it doesn't exist
            await check_and_create_table(
                conn,
                'plant_reports',
                """
                CREATE TABLE plant_reports (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    plant_id INT NOT NULL UNIQUE,
                    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    report_version INT NOT NULL DEFAULT 1,
                    plant_name VARCHAR(255) NOT NULL,
                    strain VARCHAR(255) NULL,
                    start_date DATETIME NULL,
                    end_date DATETIME NULL,
                    final_phase VARCHAR(50) NULL,
                    raw_data LONGTEXT NOT NULL COMMENT 'JSON blob with all raw data',
                    aggregated_stats TEXT NULL COMMENT 'JSON blob with aggregated statistics',
                    INDEX idx_plant_id (plant_id),
                    FOREIGN KEY (plant_id) REFERENCES plants(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

            print("\nChecking 'environment_logs' table...")

            # Create environment_logs table if it doesn't exist
            await check_and_create_table(
                conn,
                'environment_logs',
                """
                CREATE TABLE environment_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    device_id INT NOT NULL,
                    location_id INT NULL,
                    co2 INT NULL COMMENT 'CO2 level in ppm',
                    temperature DECIMAL(5,2) NULL COMMENT 'Temperature in Celsius',
                    humidity DECIMAL(5,2) NULL COMMENT 'Relative humidity in %',
                    vpd DECIMAL(5,3) NULL COMMENT 'Vapor Pressure Deficit in kPa',
                    pressure DECIMAL(6,2) NULL COMMENT 'Atmospheric pressure in hPa',
                    altitude DECIMAL(6,1) NULL COMMENT 'Calculated altitude in meters',
                    gas_resistance DECIMAL(7,2) NULL COMMENT 'Gas resistance in kOhms',
                    air_quality_score INT NULL COMMENT 'Air quality score 0-100',
                    lux DECIMAL(8,1) NULL COMMENT 'Light intensity in lux',
                    ppfd DECIMAL(6,1) NULL COMMENT 'Photosynthetic Photon Flux Density in μmol/m²/s',
                    timestamp DATETIME NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_device_id (device_id),
                    INDEX idx_location_id (location_id),
                    INDEX idx_timestamp (timestamp),
                    INDEX idx_device_timestamp (device_id, timestamp),
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

            print("\n" + "="*80)
            print("✓ Database initialization complete!")
            print("="*80 + "\n")
            return True
            
    except Exception as e:
        print(f"\n✗ Database initialization failed: {e}\n")
        return False
    finally:
        await engine.dispose()

async def verify_database_schema():
    """Verify that all required columns exist in the database."""
    print("\n" + "="*80)
    print("DATABASE SCHEMA VERIFICATION")
    print("="*80)
    
    if not DATABASE_URL:
        print("✗ DATABASE_URL not found in environment variables")
        return False
    
    engine = create_async_engine(DATABASE_URL)
    
    try:
        async with engine.begin() as conn:
            print("Verifying database schema...")
            
            # Check for required columns
            required_columns = [
                ('users', 'id'),
                ('users', 'email'),
                ('users', 'hashed_password'),
                ('users', 'first_name'),
                ('users', 'last_name'),
                ('users', 'is_active'),
                ('users', 'is_superuser'),
                ('users', 'is_verified'),
            ]
            
            all_exist = True
            for table, column in required_columns:
                result = await conn.execute(text(f"""
                    SELECT COUNT(*) as count
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = '{table}'
                    AND COLUMN_NAME = '{column}'
                """))
                row = result.fetchone()
                
                if row[0] > 0:
                    print(f"  ✓ {table}.{column} exists")
                else:
                    print(f"  ✗ {table}.{column} MISSING")
                    all_exist = False
            
            print("\n" + "="*80)
            if all_exist:
                print("✓ All required columns exist!")
            else:
                print("✗ Some columns are missing. Run init_database() to fix.")
            print("="*80 + "\n")
            
            return all_exist
            
    except Exception as e:
        print(f"\n✗ Schema verification failed: {e}\n")
        return False
    finally:
        await engine.dispose()

# Can be run standalone
if __name__ == "__main__":
    asyncio.run(init_database())