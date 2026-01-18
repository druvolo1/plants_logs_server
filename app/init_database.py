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

            # Add created_at column if it doesn't exist
            await check_and_add_column(
                conn,
                'users',
                'created_at',
                "created_at DATETIME NULL AFTER dashboard_preferences"
            )

            # Add last_login column if it doesn't exist
            await check_and_add_column(
                conn,
                'users',
                'last_login',
                "last_login DATETIME NULL AFTER created_at"
            )

            # Add login_count column if it doesn't exist
            await check_and_add_column(
                conn,
                'users',
                'login_count',
                "login_count INT NOT NULL DEFAULT 0 AFTER last_login"
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

            # Add firmware_version column if it doesn't exist (device's reported firmware version)
            await check_and_add_column(
                conn,
                'devices',
                'firmware_version',
                "firmware_version VARCHAR(50) NULL AFTER scope"
            )

            # Add mdns_hostname column if it doesn't exist (mDNS hostname for local network discovery)
            await check_and_add_column(
                conn,
                'devices',
                'mdns_hostname',
                "mdns_hostname VARCHAR(255) NULL AFTER firmware_version"
            )

            # Add ip_address column if it doesn't exist (current IP address)
            await check_and_add_column(
                conn,
                'devices',
                'ip_address',
                "ip_address VARCHAR(45) NULL AFTER mdns_hostname"
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

            # Add public visibility toggles
            await check_and_add_column(
                conn,
                'plants',
                'show_on_profile',
                "show_on_profile BOOLEAN NOT NULL DEFAULT FALSE AFTER template_id"
            )

            await check_and_add_column(
                conn,
                'plants',
                'show_as_upcoming',
                "show_as_upcoming BOOLEAN NOT NULL DEFAULT FALSE AFTER show_on_profile"
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

            print("\nChecking 'device_connections' table...")

            # Create device_connections table for tracking device-to-device relationships
            await check_and_create_table(
                conn,
                'device_connections',
                """
                CREATE TABLE device_connections (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    source_device_id INT NOT NULL COMMENT 'Device initiating the connection',
                    target_device_id INT NOT NULL COMMENT 'Device being connected to',
                    connection_type VARCHAR(50) NOT NULL COMMENT 'valve_control, power_monitoring, etc',
                    config JSON NULL COMMENT 'Connection-specific configuration (valve IDs, etc)',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    removed_at DATETIME NULL COMMENT 'Soft delete timestamp',
                    INDEX idx_source_device (source_device_id),
                    INDEX idx_target_device (target_device_id),
                    INDEX idx_connection_type (connection_type),
                    INDEX idx_active (source_device_id, removed_at),
                    FOREIGN KEY (source_device_id) REFERENCES devices(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_device_id) REFERENCES devices(id) ON DELETE CASCADE
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

            print("\nCleaning up old device-centric logging tables...")

            # Drop old log_entries table if it exists
            try:
                result = await conn.execute(text("""
                    SELECT COUNT(*) as count
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'log_entries'
                """))
                row = result.fetchone()
                if row[0] > 0:
                    print("  Dropping old 'log_entries' table...")
                    await conn.execute(text("DROP TABLE log_entries"))
                    print("  ✓ Table 'log_entries' dropped")
                else:
                    print("  ✓ Table 'log_entries' doesn't exist (already cleaned up)")
            except Exception as e:
                print(f"  Note: Error dropping log_entries table: {e}")

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

            # Drop old environment_logs table if it exists
            try:
                result = await conn.execute(text("""
                    SELECT COUNT(*) as count
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'environment_logs'
                """))
                row = result.fetchone()
                if row[0] > 0:
                    print("  Dropping old 'environment_logs' table...")
                    await conn.execute(text("DROP TABLE environment_logs"))
                    print("  ✓ Table 'environment_logs' dropped")
                else:
                    print("  ✓ Table 'environment_logs' doesn't exist (already cleaned up)")
            except Exception as e:
                print(f"  Note: Error dropping environment_logs table: {e}")

            print("\nChecking 'plant_daily_logs' table...")

            # Create plant_daily_logs table if it doesn't exist
            await check_and_create_table(
                conn,
                'plant_daily_logs',
                """
                CREATE TABLE plant_daily_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    plant_id INT NOT NULL,
                    log_date DATE NOT NULL,

                    -- Hydroponic data (min/max/avg for daily aggregation)
                    ph_min FLOAT NULL,
                    ph_max FLOAT NULL,
                    ph_avg FLOAT NULL,
                    ec_min FLOAT NULL,
                    ec_max FLOAT NULL,
                    ec_avg FLOAT NULL,
                    tds_min FLOAT NULL,
                    tds_max FLOAT NULL,
                    tds_avg FLOAT NULL,
                    water_temp_min FLOAT NULL,
                    water_temp_max FLOAT NULL,
                    water_temp_avg FLOAT NULL,

                    -- Dosing totals for the day
                    total_ph_up_ml FLOAT NULL DEFAULT 0.0,
                    total_ph_down_ml FLOAT NULL DEFAULT 0.0,
                    dosing_events_count INT NULL DEFAULT 0,

                    -- Environmental data (min/max/avg for daily aggregation)
                    co2_min INT NULL,
                    co2_max INT NULL,
                    co2_avg FLOAT NULL,
                    air_temp_min FLOAT NULL,
                    air_temp_max FLOAT NULL,
                    air_temp_avg FLOAT NULL,
                    humidity_min FLOAT NULL,
                    humidity_max FLOAT NULL,
                    humidity_avg FLOAT NULL,
                    vpd_min FLOAT NULL,
                    vpd_max FLOAT NULL,
                    vpd_avg FLOAT NULL,

                    -- Light tracking (based on threshold crossings)
                    total_light_seconds INT NULL,
                    light_cycles_count INT NULL,
                    longest_light_period_seconds INT NULL,
                    shortest_light_period_seconds INT NULL,

                    -- Metadata
                    hydro_device_id INT NULL,
                    env_device_id INT NULL,
                    last_hydro_reading DATETIME NULL,
                    last_env_reading DATETIME NULL,
                    readings_count INT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

                    -- Indexes
                    INDEX idx_plant_id (plant_id),
                    INDEX idx_log_date (log_date),
                    INDEX idx_plant_date (plant_id, log_date),

                    -- Unique constraint: one row per plant per day
                    UNIQUE KEY uq_plant_date (plant_id, log_date),

                    -- Foreign keys
                    FOREIGN KEY (plant_id) REFERENCES plants(id) ON DELETE CASCADE,
                    FOREIGN KEY (hydro_device_id) REFERENCES devices(id) ON DELETE SET NULL,
                    FOREIGN KEY (env_device_id) REFERENCES devices(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Plant-centric daily aggregated sensor logs'
                """
            )

            # Add light tracking columns to plant_daily_logs if they don't exist
            await check_and_add_column(
                conn,
                'plant_daily_logs',
                'total_light_seconds',
                "total_light_seconds INT NULL AFTER vpd_avg"
            )
            await check_and_add_column(
                conn,
                'plant_daily_logs',
                'light_cycles_count',
                "light_cycles_count INT NULL AFTER total_light_seconds"
            )
            await check_and_add_column(
                conn,
                'plant_daily_logs',
                'longest_light_period_seconds',
                "longest_light_period_seconds INT NULL AFTER light_cycles_count"
            )
            await check_and_add_column(
                conn,
                'plant_daily_logs',
                'shortest_light_period_seconds',
                "shortest_light_period_seconds INT NULL AFTER longest_light_period_seconds"
            )

            print("\nChecking 'device_posting_slots' table...")

            # Create device_posting_slots table if it doesn't exist
            await check_and_create_table(
                conn,
                'device_posting_slots',
                """
                CREATE TABLE device_posting_slots (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    device_id INT NOT NULL UNIQUE,
                    assigned_minute INT NOT NULL COMMENT 'Minutes from posting window start (0-299 for 5-hour window)',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_device_id (device_id),
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Device daily posting time slots for load balancing'
                """
            )

            print("\nChecking 'dosing_events' table...")

            # Create dosing_events table if it doesn't exist
            await check_and_create_table(
                conn,
                'dosing_events',
                """
                CREATE TABLE dosing_events (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    plant_id INT NOT NULL,
                    device_id INT NOT NULL,
                    event_date DATE NOT NULL COMMENT 'Date for quick daily queries',
                    timestamp DATETIME NOT NULL COMMENT 'Exact time of dosing event',
                    dosing_type VARCHAR(50) NOT NULL COMMENT 'ph_up, ph_down, nutrient_a, nutrient_b, etc.',
                    amount_ml FLOAT NOT NULL COMMENT 'Amount dosed in milliliters',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_plant_id (plant_id),
                    INDEX idx_device_id (device_id),
                    INDEX idx_event_date (event_date),
                    INDEX idx_plant_date (plant_id, event_date),
                    INDEX idx_device_date (device_id, event_date),
                    UNIQUE KEY uq_plant_timestamp_type (plant_id, timestamp, dosing_type),
                    FOREIGN KEY (plant_id) REFERENCES plants(id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Individual dosing events from hydro controllers'
                """
            )

            print("\nChecking 'light_events' table...")

            # Create light_events table if it doesn't exist
            await check_and_create_table(
                conn,
                'light_events',
                """
                CREATE TABLE light_events (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    plant_id INT NOT NULL,
                    device_id INT NOT NULL,
                    event_date DATE NOT NULL COMMENT 'Date for quick daily queries',
                    start_time DATETIME NOT NULL COMMENT 'When lights came ON',
                    end_time DATETIME NOT NULL COMMENT 'When lights went OFF',
                    duration_seconds INT NOT NULL COMMENT 'How long lights were ON',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_plant_id (plant_id),
                    INDEX idx_device_id (device_id),
                    INDEX idx_event_date (event_date),
                    INDEX idx_plant_date (plant_id, event_date),
                    INDEX idx_device_date (device_id, event_date),
                    UNIQUE KEY uq_plant_start_time (plant_id, start_time),
                    FOREIGN KEY (plant_id) REFERENCES plants(id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Individual light ON/OFF events from environment sensors'
                """
            )

            print("\nChecking 'notifications' table...")

            # Create notifications table if it doesn't exist
            await check_and_create_table(
                conn,
                'notifications',
                """
                CREATE TABLE notifications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    device_id VARCHAR(100) NOT NULL COMMENT 'Device identifier (matches devices.device_id)',
                    alert_type VARCHAR(100) NOT NULL COMMENT 'Alert type string (e.g., PH_OUT_OF_RANGE)',
                    alert_type_id INT NOT NULL COMMENT 'Numeric alert type ID from device enum',
                    severity ENUM('INFO', 'WARNING', 'CRITICAL') NOT NULL,
                    status ENUM('ACTIVE', 'SELF_CLEARED', 'USER_CLEARED') NOT NULL DEFAULT 'ACTIVE',
                    source VARCHAR(200) NOT NULL COMMENT 'Source component (e.g., pH Probe, EC Probe)',
                    message TEXT NOT NULL COMMENT 'Detailed alert message',
                    first_occurrence BIGINT UNSIGNED NOT NULL COMMENT 'Timestamp (millis) when first occurred',
                    last_occurrence BIGINT UNSIGNED NULL COMMENT 'Timestamp (millis) when last reported',
                    cleared_at BIGINT UNSIGNED NULL COMMENT 'Timestamp (millis) when cleared',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_device_alert (device_id, alert_type),
                    INDEX idx_status_cleared (status, cleared_at),
                    INDEX idx_device_status (device_id, status),
                    INDEX idx_severity (severity),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Device notifications and alerts'
                """
            )

            # Migrate existing notifications table to use uppercase enum values
            # This is needed if table was created with lowercase values
            try:
                print("Migrating notifications table enum values to uppercase...")
                # Check if table exists and needs migration
                result = await conn.execute(text("""
                    SELECT DATA_TYPE, COLUMN_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'notifications'
                    AND COLUMN_NAME = 'severity'
                """))
                severity_info = result.fetchone()

                if severity_info and 'info' in severity_info[1]:
                    print("  Migrating severity and status columns to uppercase enum values...")
                    # Alter the columns to use uppercase enum values
                    await conn.execute(text("""
                        ALTER TABLE notifications
                        MODIFY COLUMN severity ENUM('INFO', 'WARNING', 'CRITICAL') NOT NULL,
                        MODIFY COLUMN status ENUM('ACTIVE', 'SELF_CLEARED', 'USER_CLEARED') NOT NULL DEFAULT 'ACTIVE'
                    """))
                    print("  ✓ Migration complete - enum values are now uppercase")
                else:
                    print("  ✓ Enum values already uppercase, no migration needed")
            except Exception as e:
                print(f"  Note: Could not check/migrate enum values: {e}")

            print("\nChecking 'login_history' table...")

            # Create login_history table if it doesn't exist
            await check_and_create_table(
                conn,
                'login_history',
                """
                CREATE TABLE login_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    login_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    ip_address VARCHAR(45) NULL COMMENT 'Client IP address (IPv6 max length is 45)',
                    user_agent VARCHAR(500) NULL COMMENT 'Client user agent string',
                    INDEX idx_user_id (user_id),
                    INDEX idx_login_at (login_at),
                    INDEX idx_user_login (user_id, login_at),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='User login history (max 10 records per user)'
                """
            )

            print("\nChecking 'grower_profiles' table...")

            # Create grower_profiles table if it doesn't exist
            await check_and_create_table(
                conn,
                'grower_profiles',
                """
                CREATE TABLE grower_profiles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL UNIQUE,
                    business_name VARCHAR(255),
                    bio TEXT,
                    location VARCHAR(255),
                    website VARCHAR(500),
                    instagram VARCHAR(100),
                    is_public BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_public (is_public),
                    INDEX idx_business_name (business_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            print("\nChecking 'product_locations' table...")

            # Create product_locations table if it doesn't exist
            await check_and_create_table(
                conn,
                'product_locations',
                """
                CREATE TABLE product_locations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    store_name VARCHAR(255) NOT NULL,
                    store_link VARCHAR(500),
                    store_phone VARCHAR(20),
                    store_email VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_user (user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            print("\nChecking 'published_reports' table...")

            # Create published_reports table if it doesn't exist
            await check_and_create_table(
                conn,
                'published_reports',
                """
                CREATE TABLE published_reports (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    plant_id VARCHAR(36) NOT NULL,
                    plant_name VARCHAR(255) NOT NULL,
                    strain VARCHAR(255),
                    start_date DATE,
                    end_date DATE,
                    final_phase VARCHAR(50),
                    report_data JSON NOT NULL,
                    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    unpublished_at TIMESTAMP NULL,
                    views_count INT DEFAULT 0,
                    grower_notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_user (user_id),
                    INDEX idx_published_at (published_at),
                    INDEX idx_strain (strain),
                    INDEX idx_views (views_count),
                    INDEX idx_unpublished (unpublished_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            # Add show_on_profile column to published_reports if it doesn't exist
            await check_and_add_column(
                conn,
                'published_reports',
                'show_on_profile',
                "show_on_profile BOOLEAN NOT NULL DEFAULT TRUE AFTER grower_notes"
            )

            print("\nChecking 'upcoming_strains' table...")

            # Create upcoming_strains table if it doesn't exist
            await check_and_create_table(
                conn,
                'upcoming_strains',
                """
                CREATE TABLE upcoming_strains (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    strain_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    expected_start_date DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_user (user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            print("\nChecking 'strain_reviews' table...")

            # Create strain_reviews table if it doesn't exist
            await check_and_create_table(
                conn,
                'strain_reviews',
                """
                CREATE TABLE strain_reviews (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    published_report_id INT NOT NULL,
                    reviewer_id INT NOT NULL,
                    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
                    comment TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (published_report_id) REFERENCES published_reports(id) ON DELETE CASCADE,
                    FOREIGN KEY (reviewer_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_review (published_report_id, reviewer_id),
                    INDEX idx_report (published_report_id),
                    INDEX idx_reviewer (reviewer_id),
                    INDEX idx_rating (rating)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            print("\nChecking 'review_responses' table...")

            # Create review_responses table if it doesn't exist
            await check_and_create_table(
                conn,
                'review_responses',
                """
                CREATE TABLE review_responses (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    review_id INT NOT NULL,
                    grower_id INT NOT NULL,
                    response_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (review_id) REFERENCES strain_reviews(id) ON DELETE CASCADE,
                    FOREIGN KEY (grower_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_response (review_id),
                    INDEX idx_review (review_id),
                    INDEX idx_grower (grower_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            print("\nChecking 'admin_settings' table...")

            # Create admin_settings table if it doesn't exist
            await check_and_create_table(
                conn,
                'admin_settings',
                """
                CREATE TABLE admin_settings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    setting_key VARCHAR(100) NOT NULL UNIQUE,
                    setting_value TEXT,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_key (setting_key)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )

            # Insert default admin settings
            try:
                result = await conn.execute(text("""
                    SELECT COUNT(*) as count FROM admin_settings
                    WHERE setting_key = 'allow_anonymous_browsing'
                """))
                row = result.fetchone()

                if row[0] == 0:
                    print("  Inserting default admin settings...")
                    await conn.execute(text("""
                        INSERT INTO admin_settings (setting_key, setting_value, description)
                        VALUES ('allow_anonymous_browsing', 'true', 'Allow non-logged-in users to browse published reports and grower profiles')
                    """))
                    print("  ✓ Default admin settings inserted")
                else:
                    print("  ✓ Admin settings already exist")
            except Exception as e:
                print(f"  Note: Could not insert default admin settings: {e}")

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