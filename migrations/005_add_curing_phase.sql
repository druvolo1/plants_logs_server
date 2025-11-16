-- Migration 005: Add curing phase support
-- Adds expected_curing_days to plants and phase_templates tables

-- Add expected_curing_days to plants table
ALTER TABLE plants ADD COLUMN expected_curing_days INT NULL AFTER expected_drying_days;

-- Add expected_curing_days to phase_templates table
ALTER TABLE phase_templates ADD COLUMN expected_curing_days INT NULL AFTER expected_drying_days;
