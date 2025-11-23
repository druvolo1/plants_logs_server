-- Migration 006: Add locations support with arbitrary nesting
-- Adds locations table, location_shares table, and location_id to devices and plants tables

-- Create locations table
CREATE TABLE IF NOT EXISTS locations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    parent_id INT NULL,
    user_id INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES locations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_parent_id (parent_id),
    INDEX idx_user_id (user_id)
);

-- Create location_shares table
CREATE TABLE IF NOT EXISTS location_shares (
    id INT AUTO_INCREMENT PRIMARY KEY,
    location_id INT NOT NULL,
    owner_user_id INT NOT NULL,
    shared_with_user_id INT NULL,
    share_code VARCHAR(12) UNIQUE NOT NULL,
    permission_level VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    accepted_at DATETIME NULL,
    revoked_at DATETIME NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE,
    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (shared_with_user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_location_id (location_id),
    INDEX idx_share_code (share_code),
    INDEX idx_owner_user_id (owner_user_id),
    INDEX idx_shared_with_user_id (shared_with_user_id)
);

-- Add location_id to devices table
ALTER TABLE devices ADD COLUMN location_id INT NULL AFTER user_id;
ALTER TABLE devices ADD FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL;
ALTER TABLE devices ADD INDEX idx_location_id (location_id);

-- Add location_id to plants table
ALTER TABLE plants ADD COLUMN location_id INT NULL AFTER user_id;
ALTER TABLE plants ADD FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL;
ALTER TABLE plants ADD INDEX idx_location_id (location_id);
