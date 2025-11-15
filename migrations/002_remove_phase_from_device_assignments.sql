-- Migration: Remove phase column from device_assignments
-- Phase tracking belongs to Plant, not DeviceAssignment
-- A plant can change phases while staying on the same device

-- Check if column exists before dropping
SET @exist := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'device_assignments'
    AND COLUMN_NAME = 'phase'
);

SET @sqlstmt := IF(
    @exist > 0,
    'ALTER TABLE device_assignments DROP COLUMN phase',
    'SELECT "Column phase does not exist in device_assignments" AS status'
);

PREPARE stmt FROM @sqlstmt;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SELECT 'Migration 002 completed: Removed phase column from device_assignments' AS status;
