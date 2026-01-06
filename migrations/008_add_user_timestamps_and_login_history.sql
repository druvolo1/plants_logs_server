-- Migration 008: Add user creation timestamp and login tracking
-- Adds created_at, last_login, login_count to users table
-- Creates login_history table with automatic 10-record-per-user limit

-- Add timestamp and login tracking fields to users table
ALTER TABLE users
    ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER dashboard_preferences,
    ADD COLUMN last_login DATETIME NULL AFTER created_at,
    ADD COLUMN login_count INT NOT NULL DEFAULT 0 AFTER last_login;

-- Add indexes for efficient queries
ALTER TABLE users ADD INDEX idx_created_at (created_at);
ALTER TABLE users ADD INDEX idx_last_login (last_login);

-- Create login_history table
CREATE TABLE IF NOT EXISTS login_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    login_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(500) NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_login_at (login_at),
    INDEX idx_user_login (user_id, login_at)
);
