-- Migration: Add plant lifecycle and device assignment support
-- Run this on your database to add the new schema changes

-- 1. Add device_type to devices table
ALTER TABLE devices
ADD COLUMN device_type VARCHAR(50) DEFAULT 'feeding_system' AFTER is_online;

-- 2. Create device_assignments table
CREATE TABLE IF NOT EXISTS device_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    plant_id INT NOT NULL,
    device_id INT NOT NULL,
    phase VARCHAR(50) NOT NULL,
    assigned_at DATETIME NOT NULL,
    removed_at DATETIME NULL,
    FOREIGN KEY (plant_id) REFERENCES plants(id) ON DELETE CASCADE,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    INDEX idx_plant_phase (plant_id, phase),
    INDEX idx_device (device_id),
    INDEX idx_assigned_at (assigned_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Add new lifecycle fields to plants table
ALTER TABLE plants
ADD COLUMN status VARCHAR(50) NOT NULL DEFAULT 'feeding' AFTER display_order,
ADD COLUMN current_phase VARCHAR(50) NULL AFTER status,
ADD COLUMN harvest_date DATETIME NULL AFTER current_phase,
ADD COLUMN cure_start_date DATETIME NULL AFTER harvest_date,
ADD COLUMN cure_end_date DATETIME NULL AFTER cure_start_date;

-- 4. Make device_id nullable in plants table (for backward compatibility)
ALTER TABLE plants
MODIFY COLUMN device_id INT NULL;

-- 5. Add phase column to log_entries table
ALTER TABLE log_entries
ADD COLUMN phase VARCHAR(50) NULL AFTER timestamp;

-- 6. Update existing plants to have correct status
-- Plants with end_date are finished, others are feeding
UPDATE plants
SET status = CASE
    WHEN end_date IS NOT NULL THEN 'finished'
    ELSE 'feeding'
END
WHERE status = 'feeding';

-- 7. Update existing plants to have current_phase based on status
UPDATE plants
SET current_phase = CASE
    WHEN status = 'feeding' THEN 'feeding'
    ELSE NULL
END
WHERE current_phase IS NULL;

COMMIT;
