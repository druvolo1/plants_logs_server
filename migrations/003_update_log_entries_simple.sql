-- Migration: Update log_entries table to new schema (simplified version)
-- Changes from column-per-sensor to event-based structure

-- Drop old log_entries table and recreate with new structure
DROP TABLE IF EXISTS log_entries;

CREATE TABLE log_entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    plant_id INT NOT NULL,
    event_type VARCHAR(20) NOT NULL,
    sensor_name VARCHAR(50) NULL,
    value FLOAT NULL,
    dose_type VARCHAR(10) NULL,
    dose_amount_ml FLOAT NULL,
    timestamp DATETIME NOT NULL,
    phase VARCHAR(50) NULL,
    INDEX idx_plant_id (plant_id),
    INDEX idx_timestamp (timestamp),
    FOREIGN KEY (plant_id) REFERENCES plants(id) ON DELETE CASCADE
) ENGINE=InnoDB;

SELECT 'Migration 003 completed: log_entries table recreated with new schema' AS status;
