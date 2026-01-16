-- Migration to convert plant start_date and end_date from DATETIME to DATE
-- This removes the time component from plant dates for simpler comparison logic

-- Step 1: Add new DATE columns
ALTER TABLE plants ADD COLUMN start_date_new DATE;
ALTER TABLE plants ADD COLUMN end_date_new DATE;

-- Step 2: Copy data, converting datetime to date
UPDATE plants SET start_date_new = DATE(start_date);
UPDATE plants SET end_date_new = DATE(end_date) WHERE end_date IS NOT NULL;

-- Step 3: Drop old columns
ALTER TABLE plants DROP COLUMN start_date;
ALTER TABLE plants DROP COLUMN end_date;

-- Step 4: Rename new columns to original names
ALTER TABLE plants CHANGE COLUMN start_date_new start_date DATE NOT NULL;
ALTER TABLE plants CHANGE COLUMN end_date_new end_date DATE;

-- Verify the changes
SELECT id, plant_id, name, start_date, end_date FROM plants LIMIT 5;
