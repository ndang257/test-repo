-- Obeta Database Setup Script (Updated for DATETIME support)
-- Run with: mysql -u root -p < setup_obeta_db.sql
-- Or from MySQL prompt: source setup_obeta_db.sql

-- Create database
CREATE DATABASE IF NOT EXISTS obeta_db;
USE obeta_db;

SELECT 'Creating Obeta Database...' as Status;

-- Drop old tables
DROP TABLE IF EXISTS pick_data;
DROP TABLE IF EXISTS product_data;

-- Create product_data table
CREATE TABLE product_data (
    product_id VARCHAR(255) NOT NULL PRIMARY KEY,
    description TEXT,
    product_group VARCHAR(255)
);

-- Create pick_data table with DATETIME field
CREATE TABLE pick_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id VARCHAR(255),
    warehouse_section VARCHAR(255),
    origin INT,
    order_number VARCHAR(255),
    position_in_order VARCHAR(255),
    pick_volume INT,
    quantity_unit VARCHAR(255),
    date DATETIME,                     -- changed from DATE → DATETIME
    FOREIGN KEY (product_id) REFERENCES product_data(product_id)
);

SELECT 'Tables created successfully!' as Status;

-- Enable local file loading
SET GLOBAL local_infile = 1;

-- Import product_data
SELECT 'Importing product data...' as Status;

LOAD DATA LOCAL INFILE 'Your path/002 product_data.csv' 
INTO TABLE product_data
CHARACTER SET latin1
FIELDS TERMINATED BY ',' 
OPTIONALLY ENCLOSED BY '"' 
LINES TERMINATED BY '\n' 
(product_id, description, product_group);

-- Import pick_data with full DATETIME support
SELECT 'Importing pick data...' as Status;

LOAD DATA LOCAL INFILE 'Your path/003 pick_data.csv'
INTO TABLE pick_data
CHARACTER SET latin1
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(product_id, warehouse_section, origin, order_number, position_in_order, pick_volume, quantity_unit, @datetime_str)
SET date = STR_TO_DATE(@datetime_str, '%Y-%m-%d %H:%i:%s');

-- Create indexes
SELECT 'Creating indexes...' as Status;
CREATE INDEX idx_pick_data_product_id ON pick_data(product_id);
CREATE INDEX idx_pick_data_date ON pick_data(date);
CREATE INDEX idx_pick_data_warehouse_section ON pick_data(warehouse_section);
CREATE INDEX idx_product_data_product_group ON product_data(product_group);

-- Display import summary
SELECT 'Database setup complete!' as Status;

SELECT 
    'Product Data' as Table_Name,
    COUNT(*) as Record_Count
FROM product_data
UNION ALL
SELECT 
    'Pick Data' as Table_Name,
    COUNT(*) as Record_Count
FROM pick_data;

-- Show structures
SELECT 'Table Structures:' as Info;
DESCRIBE product_data;
DESCRIBE pick_data;

-- Sample queries
SELECT 'Sample Data - Top 5 Products:' as Info;
SELECT product_id, description, product_group 
FROM product_data 
LIMIT 5;

SELECT 'Sample Data - Recent Picks:' as Info;
SELECT p.product_id, p.description, pk.warehouse_section, pk.pick_volume, pk.date
FROM product_data p
JOIN pick_data pk ON p.product_id = pk.product_id
ORDER BY pk.date DESC
LIMIT 5;
