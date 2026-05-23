-- Olist 九张业务表 DDL（Utf8MB4，便于葡语评论）
-- 字段名与主流 Kaggle 版 Brazilian E-Commerce 对齐；若有新增列可自行 ALTER。

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS order_reviews;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS sellers;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS geolocation;
DROP TABLE IF EXISTS product_category_name_translation;

CREATE TABLE orders (
    order_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL,
    order_status VARCHAR(32) NOT NULL,
    order_purchase_timestamp DATETIME NULL,
    order_approved_at DATETIME NULL,
    order_delivered_carrier_date DATETIME NULL,
    order_delivered_customer_date DATETIME NULL,
    order_estimated_delivery_date DATETIME NULL,
    INDEX idx_orders_customer (customer_id),
    INDEX idx_orders_status (order_status),
    INDEX idx_orders_purchase (order_purchase_timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE order_items (
    order_id VARCHAR(32) NOT NULL,
    order_item_id INT NOT NULL,
    product_id VARCHAR(32) NOT NULL,
    seller_id VARCHAR(32) NOT NULL,
    shipping_limit_date DATETIME NULL,
    price DECIMAL(12, 2) NOT NULL,
    freight_value DECIMAL(12, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (order_id, order_item_id),
    INDEX idx_items_product (product_id),
    INDEX idx_items_seller (seller_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE customers (
    customer_id VARCHAR(32) PRIMARY KEY,
    customer_unique_id VARCHAR(32) NOT NULL,
    customer_zip_code_prefix VARCHAR(16) NOT NULL,
    customer_city VARCHAR(128) NOT NULL,
    customer_state CHAR(2) NOT NULL,
    INDEX idx_customer_state (customer_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE sellers (
    seller_id VARCHAR(32) PRIMARY KEY,
    seller_zip_code_prefix VARCHAR(16) NOT NULL,
    seller_city VARCHAR(128) NOT NULL,
    seller_state CHAR(2) NOT NULL,
    INDEX idx_seller_state (seller_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE products (
    product_id VARCHAR(32) PRIMARY KEY,
    product_category_name VARCHAR(128) NULL,
    product_name_lenght SMALLINT NULL COMMENT 'Kaggle CSV 原版拼写（非 length），与入库列名一致',
    product_description_lenght SMALLINT NULL COMMENT '同上 *_lenght',
    product_photos_qty SMALLINT NULL,
    product_weight_g INT NULL,
    product_length_cm INT NULL,
    product_height_cm INT NULL,
    product_width_cm INT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE payments (
    order_id VARCHAR(32) NOT NULL,
    payment_sequential SMALLINT NOT NULL,
    payment_type VARCHAR(48) NOT NULL,
    payment_installments SMALLINT NOT NULL,
    payment_value DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (order_id, payment_sequential),
    INDEX idx_pay_type (payment_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE order_reviews (
    review_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id VARCHAR(32) NOT NULL,
    review_score SMALLINT NOT NULL,
    review_comment_title VARCHAR(256) NULL,
    review_comment_message TEXT NULL,
    review_creation_date DATETIME NULL,
    review_answer_timestamp DATETIME NULL,
    INDEX idx_reviews_order (order_id),
    INDEX idx_review_score (review_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE geolocation (
    geolocation_zip_code_prefix VARCHAR(16) NOT NULL,
    geolocation_lat DECIMAL(10, 8) NOT NULL,
    geolocation_lng DECIMAL(11, 8) NOT NULL,
    geolocation_city VARCHAR(128) NOT NULL,
    geolocation_state CHAR(2) NOT NULL,
    INDEX idx_geo_zip_prefix (geolocation_zip_code_prefix)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE product_category_name_translation (
    product_category_name VARCHAR(128) PRIMARY KEY,
    product_category_name_english VARCHAR(128) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;
