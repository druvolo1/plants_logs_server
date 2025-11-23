-- Migration 007: Add environment sensor support
-- Adds environment_logs table and device settings columns

-- Create environment_logs table for environmental sensor data
CREATE TABLE IF NOT EXISTS environment_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    location_id INT NULL,

    -- Air Quality readings
    co2 INT NULL COMMENT 'CO2 level in ppm',
    temperature DECIMAL(5,2) NULL COMMENT 'Temperature in Celsius',
    humidity DECIMAL(5,2) NULL COMMENT 'Relative humidity in %',
    vpd DECIMAL(5,3) NULL COMMENT 'Vapor Pressure Deficit in kPa',

    -- Atmospheric readings
    pressure DECIMAL(6,2) NULL COMMENT 'Atmospheric pressure in hPa',
    altitude DECIMAL(6,1) NULL COMMENT 'Calculated altitude in meters',
    gas_resistance DECIMAL(7,2) NULL COMMENT 'Gas resistance in kOhms',
    air_quality_score INT NULL COMMENT 'Air quality score 0-100',

    -- Light readings
    lux DECIMAL(8,1) NULL COMMENT 'Light intensity in lux',
    ppfd DECIMAL(6,1) NULL COMMENT 'Photosynthetic Photon Flux Density in μmol/m²/s',

    timestamp DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL,
    INDEX idx_device_id (device_id),
    INDEX idx_location_id (location_id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_device_timestamp (device_id, timestamp)
);

-- Add device settings columns for environment sensors
ALTER TABLE devices ADD COLUMN settings JSON NULL COMMENT 'Device-specific settings (temp scale, update interval, etc.)';
