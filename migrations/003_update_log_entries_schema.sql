-- Migration: Update log_entries table to new schema
-- Changes from legacy columns to new event-based structure

-- Step 1: Add new columns if they don't exist

-- Add event_type column (sensor or dosing)
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'event_type'
);
SET @sqlstmt := IF(
    @exist = 0,
    'ALTER TABLE log_entries ADD COLUMN event_type VARCHAR(20) NOT NULL DEFAULT "sensor" AFTER plant_id',
    'SELECT "Column event_type already exists" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add sensor_name column
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'sensor_name'
);
SET @sqlstmt := IF(
    @exist = 0,
    'ALTER TABLE log_entries ADD COLUMN sensor_name VARCHAR(50) NULL AFTER event_type',
    'SELECT "Column sensor_name already exists" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add value column
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'value'
);
SET @sqlstmt := IF(
    @exist = 0,
    'ALTER TABLE log_entries ADD COLUMN value FLOAT NULL AFTER sensor_name',
    'SELECT "Column value already exists" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add dose_type column
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'dose_type'
);
SET @sqlstmt := IF(
    @exist = 0,
    'ALTER TABLE log_entries ADD COLUMN dose_type VARCHAR(10) NULL AFTER value',
    'SELECT "Column dose_type already exists" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add dose_amount_ml column
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'dose_amount_ml'
);
SET @sqlstmt := IF(
    @exist = 0,
    'ALTER TABLE log_entries ADD COLUMN dose_amount_ml FLOAT NULL AFTER dose_type',
    'SELECT "Column dose_amount_ml already exists" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add phase column (to track which phase plant was in when log was created)
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'phase'
);
SET @sqlstmt := IF(
    @exist = 0,
    'ALTER TABLE log_entries ADD COLUMN phase VARCHAR(50) NULL',
    'SELECT "Column phase already exists" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 2: Migrate data from old columns to new columns (if old columns exist)

-- Migrate from log_type to event_type
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'log_type'
);
SET @sqlstmt := IF(
    @exist > 0,
    'UPDATE log_entries SET event_type = log_type WHERE event_type = "sensor"',
    'SELECT "Column log_type does not exist, skipping migration" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Migrate from reading to value (for sensor readings)
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'reading'
);
SET @sqlstmt := IF(
    @exist > 0,
    'UPDATE log_entries SET value = reading WHERE value IS NULL',
    'SELECT "Column reading does not exist, skipping migration" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Migrate from amount to dose_amount_ml (for dosing events)
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'amount'
);
SET @sqlstmt := IF(
    @exist > 0,
    'UPDATE log_entries SET dose_amount_ml = amount WHERE dose_amount_ml IS NULL',
    'SELECT "Column amount does not exist, skipping migration" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 3: Drop old columns if they exist

-- Drop log_type column
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'log_type'
);
SET @sqlstmt := IF(
    @exist > 0,
    'ALTER TABLE log_entries DROP COLUMN log_type',
    'SELECT "Column log_type does not exist" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Drop reading column
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'reading'
);
SET @sqlstmt := IF(
    @exist > 0,
    'ALTER TABLE log_entries DROP COLUMN reading',
    'SELECT "Column reading does not exist" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Drop amount column
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'amount'
);
SET @sqlstmt := IF(
    @exist > 0,
    'ALTER TABLE log_entries DROP COLUMN amount',
    'SELECT "Column amount does not exist" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Drop sensor column (replaced by sensor_name)
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'log_entries'
    AND COLUMN_NAME = 'sensor'
);
SET @sqlstmt := IF(
    @exist > 0,
    'ALTER TABLE log_entries DROP COLUMN sensor',
    'SELECT "Column sensor does not exist" AS status'
);
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Verify final schema
SELECT 'Migration 003 completed: Updated log_entries schema' AS status;
DESCRIBE log_entries;
