-- Run this to get the production database schema
-- mysql -u app_user -p -h 172.16.1.150 plant_logs < export_prod_schema.sql > prod_schema_export.txt

-- Show all table structures
SHOW CREATE TABLE users;
SHOW CREATE TABLE oauth_accounts;
SHOW CREATE TABLE devices;
SHOW CREATE TABLE device_shares;
SHOW CREATE TABLE device_assignments;
SHOW CREATE TABLE plants;
SHOW CREATE TABLE phase_history;
SHOW CREATE TABLE log_entries;
