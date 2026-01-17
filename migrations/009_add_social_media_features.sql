-- Migration 009: Add social media features
-- Creates tables for grower profiles, published reports, reviews, and product locations
-- Enables public sharing of plant reports and community engagement

-- 1. Grower Profiles
CREATE TABLE IF NOT EXISTS grower_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,

    -- Business Information
    business_name VARCHAR(255),
    bio TEXT,
    location VARCHAR(255),
    website VARCHAR(500),
    instagram VARCHAR(100),

    -- System Fields
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_public (is_public),
    INDEX idx_business_name (business_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Product Locations
CREATE TABLE IF NOT EXISTS product_locations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,

    store_name VARCHAR(255) NOT NULL,
    store_link VARCHAR(500),
    store_phone VARCHAR(20),
    store_email VARCHAR(255),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Published Reports
CREATE TABLE IF NOT EXISTS published_reports (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- Links
    user_id INT NOT NULL,
    plant_id VARCHAR(36) NOT NULL,

    -- Frozen Report Data
    plant_name VARCHAR(255) NOT NULL,
    strain VARCHAR(255),
    start_date DATE,
    end_date DATE,
    final_phase VARCHAR(50),

    -- Full report JSON
    report_data JSON NOT NULL,

    -- Publishing Metadata
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    unpublished_at TIMESTAMP NULL,
    views_count INT DEFAULT 0,

    -- Optional grower notes
    grower_notes TEXT,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id),
    INDEX idx_published_at (published_at),
    INDEX idx_strain (strain),
    INDEX idx_views (views_count),
    INDEX idx_unpublished (unpublished_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Upcoming Strains
CREATE TABLE IF NOT EXISTS upcoming_strains (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,

    strain_name VARCHAR(255) NOT NULL,
    description TEXT,
    expected_start_date DATE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Strain Reviews
CREATE TABLE IF NOT EXISTS strain_reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,

    published_report_id INT NOT NULL,
    reviewer_id INT NOT NULL,

    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (published_report_id) REFERENCES published_reports(id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_id) REFERENCES users(id) ON DELETE CASCADE,

    UNIQUE KEY unique_review (published_report_id, reviewer_id),
    INDEX idx_report (published_report_id),
    INDEX idx_reviewer (reviewer_id),
    INDEX idx_rating (rating)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Review Responses
CREATE TABLE IF NOT EXISTS review_responses (
    id INT AUTO_INCREMENT PRIMARY KEY,

    review_id INT NOT NULL,
    grower_id INT NOT NULL,

    response_text TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (review_id) REFERENCES strain_reviews(id) ON DELETE CASCADE,
    FOREIGN KEY (grower_id) REFERENCES users(id) ON DELETE CASCADE,

    UNIQUE KEY unique_response (review_id),
    INDEX idx_review (review_id),
    INDEX idx_grower (grower_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. Admin Settings
CREATE TABLE IF NOT EXISTS admin_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(100) NOT NULL UNIQUE,
    setting_value TEXT,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_key (setting_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default setting for anonymous browsing
INSERT INTO admin_settings (setting_key, setting_value, description)
VALUES ('allow_anonymous_browsing', 'true', 'Allow non-logged-in users to browse published reports and grower profiles')
ON DUPLICATE KEY UPDATE setting_key=setting_key;
