-- Migration 004: Add batch_number and expected phase durations to plants table

-- Add batch_number column (alphanumeric, optional)
ALTER TABLE plants ADD COLUMN batch_number VARCHAR(100) NULL AFTER name;

-- Add expected phase duration columns (in days, optional - can override template)
ALTER TABLE plants ADD COLUMN expected_seed_days INT NULL;
ALTER TABLE plants ADD COLUMN expected_clone_days INT NULL;
ALTER TABLE plants ADD COLUMN expected_veg_days INT NULL;
ALTER TABLE plants ADD COLUMN expected_flower_days INT NULL;
ALTER TABLE plants ADD COLUMN expected_drying_days INT NULL;

-- Add template_id column (references phase_templates table, optional)
ALTER TABLE plants ADD COLUMN template_id INT NULL;

-- Create phase_templates table for reusable phase duration templates
CREATE TABLE IF NOT EXISTS phase_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT NULL,
    user_id INT NOT NULL,

    -- Expected durations for each phase (in days)
    expected_seed_days INT NULL,
    expected_clone_days INT NULL,
    expected_veg_days INT NULL,
    expected_flower_days INT NULL,
    expected_drying_days INT NULL,

    created_at DATETIME NOT NULL,
    updated_at DATETIME NULL,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB;

SELECT 'Migration 004 completed: Added batch_number and phase duration fields' AS status;
