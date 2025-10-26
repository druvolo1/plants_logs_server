from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}?charset=utf8mb4"
engine = create_engine(DB_URL)

schema_sql = """
CREATE DATABASE IF NOT EXISTS plant_logs CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE plant_logs;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(1024) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    is_verified BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS plants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    user_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS dosing_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    plant_id INT NOT NULL,
    event_type VARCHAR(50),
    ph DECIMAL(5,3),
    dose_type VARCHAR(10),
    dose_amount_ml DECIMAL(5,2),
    timestamp TIMESTAMP NOT NULL,
    FOREIGN KEY (plant_id) REFERENCES plants(id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_plant_timestamp (plant_id, timestamp)
);

CREATE TABLE IF NOT EXISTS feeding_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    plant_id INT NOT NULL,
    event_type VARCHAR(50),
    message TEXT,
    status VARCHAR(50),
    timestamp TIMESTAMP NOT NULL,
    plant_ip VARCHAR(255),
    FOREIGN KEY (plant_id) REFERENCES plants(id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_plant_timestamp (plant_id, timestamp)
);

CREATE TABLE IF NOT EXISTS ph_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    plant_id INT NOT NULL,
    event_type VARCHAR(50),
    sensor_name VARCHAR(50),
    value DECIMAL(5,3),
    timestamp TIMESTAMP NOT NULL,
    FOREIGN KEY (plant_id) REFERENCES plants(id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_plant_timestamp (plant_id, timestamp)
);
"""

with engine.connect() as connection:
    for statement in schema_sql.split(';'):
        if statement.strip():
            connection.execute(text(statement))
    print("Database and tables created successfully.")