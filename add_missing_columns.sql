-- Add missing columns to plants table
-- Run this on your dev database: plant_logs_dev

USE plant_logs_dev;

-- Add plant_id column (if it doesn't exist)
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'plant_logs_dev' AND TABLE_NAME = 'plants' AND COLUMN_NAME = 'plant_id');
SET @sqlstmt := IF(@exist = 0, 'ALTER TABLE plants ADD COLUMN plant_id VARCHAR(64) NULL UNIQUE AFTER id', 'SELECT "plant_id already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;

-- Add system_id column (if it doesn't exist)
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'plant_logs_dev' AND TABLE_NAME = 'plants' AND COLUMN_NAME = 'system_id');
SET @sqlstmt := IF(@exist = 0, 'ALTER TABLE plants ADD COLUMN system_id VARCHAR(255) NULL AFTER name', 'SELECT "system_id already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;

-- Add end_date column (if it doesn't exist)
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'plant_logs_dev' AND TABLE_NAME = 'plants' AND COLUMN_NAME = 'end_date');
SET @sqlstmt := IF(@exist = 0, 'ALTER TABLE plants ADD COLUMN end_date DATETIME NULL AFTER start_date', 'SELECT "end_date already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;

-- Add yield_grams column (if it doesn't exist)
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'plant_logs_dev' AND TABLE_NAME = 'plants' AND COLUMN_NAME = 'yield_grams');
SET @sqlstmt := IF(@exist = 0, 'ALTER TABLE plants ADD COLUMN yield_grams FLOAT NULL AFTER end_date', 'SELECT "yield_grams already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;

-- Add display_order column (if it doesn't exist)
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'plant_logs_dev' AND TABLE_NAME = 'plants' AND COLUMN_NAME = 'display_order');
SET @sqlstmt := IF(@exist = 0, 'ALTER TABLE plants ADD COLUMN display_order INT NULL DEFAULT 0 AFTER yield_grams', 'SELECT "display_order already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;

-- Add status column (if it doesn't exist)
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'plant_logs_dev' AND TABLE_NAME = 'plants' AND COLUMN_NAME = 'status');
SET @sqlstmt := IF(@exist = 0, 'ALTER TABLE plants ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT "created" AFTER display_order', 'SELECT "status already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;

-- Add cure_start_date column (if it doesn't exist)
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'plant_logs_dev' AND TABLE_NAME = 'plants' AND COLUMN_NAME = 'cure_start_date');
SET @sqlstmt := IF(@exist = 0, 'ALTER TABLE plants ADD COLUMN cure_start_date DATETIME NULL AFTER harvest_date', 'SELECT "cure_start_date already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;

-- Add cure_end_date column (if it doesn't exist)
SET @exist := (SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'plant_logs_dev' AND TABLE_NAME = 'plants' AND COLUMN_NAME = 'cure_end_date');
SET @sqlstmt := IF(@exist = 0, 'ALTER TABLE plants ADD COLUMN cure_end_date DATETIME NULL AFTER cure_start_date', 'SELECT "cure_end_date already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;

-- Create index on plant_id if it doesn't exist
SET @exist := (SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = 'plant_logs_dev' AND TABLE_NAME = 'plants' AND INDEX_NAME = 'idx_plant_id');
SET @sqlstmt := IF(@exist = 0, 'CREATE INDEX idx_plant_id ON plants(plant_id)', 'SELECT "idx_plant_id already exists"');
PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;

-- Verify the changes
DESCRIBE plants;

SELECT 'Migration completed successfully!' AS status;
