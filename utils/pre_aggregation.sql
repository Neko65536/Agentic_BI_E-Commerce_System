-- 预聚合层：物理汇总表 mv_*（一次计算入库，刷新可 TRUNCATE + 重新 INSERT）
-- 作业中称“预聚合视图”，MySQL 无原生物化视图，本项目用同名表承接；查询体验等价。

SET NAMES utf8mb4;

DROP TABLE IF EXISTS mv_monthly_sales;
CREATE TABLE mv_monthly_sales (
  `year_month` CHAR(7) NOT NULL,
  total_gmv DECIMAL(18,2) NOT NULL,
  total_orders INT NOT NULL,
  avg_basket DECIMAL(18,2) NOT NULL,
  total_freight DECIMAL(18,2) NOT NULL,
  PRIMARY KEY (`year_month`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO mv_monthly_sales (
  `year_month`, total_gmv, total_orders, avg_basket, total_freight
)
SELECT DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS `year_month`,
       SUM(oi.price + oi.freight_value) AS total_gmv,
       COUNT(DISTINCT o.order_id) AS total_orders,
       SUM(oi.price + oi.freight_value) / NULLIF(COUNT(DISTINCT o.order_id), 0) AS avg_basket,
       SUM(oi.freight_value) AS total_freight
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_purchase_timestamp IS NOT NULL
GROUP BY 1;

DROP TABLE IF EXISTS mv_state_sales;
CREATE TABLE mv_state_sales (
  `year_month` CHAR(7) NOT NULL,
  customer_state CHAR(2) NOT NULL,
  total_gmv DECIMAL(18,2) NOT NULL,
  total_orders INT NOT NULL,
  unique_customers INT NOT NULL,
  PRIMARY KEY (`year_month`, customer_state),
  INDEX idx_mv_state_sales_state (customer_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO mv_state_sales (
  `year_month`, customer_state, total_gmv, total_orders, unique_customers
)
SELECT DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS `year_month`,
       c.customer_state,
       SUM(oi.price + oi.freight_value) AS total_gmv,
       COUNT(DISTINCT o.order_id) AS total_orders,
       COUNT(DISTINCT c.customer_unique_id) AS unique_customers
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_purchase_timestamp IS NOT NULL
GROUP BY 1, 2;

DROP TABLE IF EXISTS mv_category_sales;
CREATE TABLE mv_category_sales (
  `year_month` CHAR(7) NOT NULL,
  product_category_english VARCHAR(160) NOT NULL,
  total_gmv DECIMAL(18,2) NOT NULL,
  total_orders INT NOT NULL,
  avg_price DECIMAL(18,4) NOT NULL,
  PRIMARY KEY (`year_month`, product_category_english),
  INDEX idx_mv_cat_ym (`year_month`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO mv_category_sales (
  `year_month`, product_category_english, total_gmv, total_orders, avg_price
)
SELECT DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS `year_month`,
       COALESCE(t.product_category_name_english, p.product_category_name, 'UNKNOWN') AS product_category_english,
       SUM(oi.price + oi.freight_value) AS total_gmv,
       COUNT(DISTINCT o.order_id) AS total_orders,
       AVG(oi.price) AS avg_price
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
LEFT JOIN product_category_name_translation t
  ON t.product_category_name = p.product_category_name
WHERE o.order_purchase_timestamp IS NOT NULL
GROUP BY 1, 2;

DROP TABLE IF EXISTS mv_delivery_perf;
CREATE TABLE mv_delivery_perf (
  `year_month` CHAR(7) NOT NULL,
  customer_state CHAR(2) NOT NULL,
  avg_delivery_days DECIMAL(14,4) NOT NULL,
  on_time_rate DECIMAL(7,4) NOT NULL,
  delayed_orders INT NOT NULL,
  PRIMARY KEY (`year_month`, customer_state),
  INDEX idx_delivery_state (customer_state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO mv_delivery_perf (
  `year_month`, customer_state, avg_delivery_days, on_time_rate, delayed_orders
)
SELECT DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS `year_month`,
       c.customer_state,
       AVG(DATEDIFF(o.order_delivered_customer_date, o.order_purchase_timestamp)) AS avg_delivery_days,
       AVG(CASE WHEN o.order_delivered_customer_date <= o.order_estimated_delivery_date THEN 1 ELSE 0 END) AS on_time_rate,
       SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 ELSE 0 END) AS delayed_orders
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_purchase_timestamp IS NOT NULL
  AND o.order_delivered_customer_date IS NOT NULL
  AND o.order_estimated_delivery_date IS NOT NULL
GROUP BY 1, 2;

DROP TABLE IF EXISTS mv_seller_perf;
CREATE TABLE mv_seller_perf (
  `year_month` CHAR(7) NOT NULL,
  seller_id VARCHAR(32) NOT NULL,
  seller_state CHAR(2) NOT NULL,
  total_gmv DECIMAL(18,2) NOT NULL,
  total_orders INT NOT NULL,
  avg_review_score DECIMAL(8,4) NULL,
  PRIMARY KEY (`year_month`, seller_id),
  INDEX idx_mv_seller (seller_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO mv_seller_perf (
  `year_month`, seller_id, seller_state, total_gmv, total_orders, avg_review_score
)
SELECT DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS `year_month`,
       oi.seller_id,
       s.seller_state,
       SUM(oi.price + oi.freight_value) AS total_gmv,
       COUNT(DISTINCT o.order_id) AS total_orders,
       AVG(CAST(rv.review_score AS DECIMAL(10, 4))) AS avg_review_score
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
JOIN sellers s ON s.seller_id = oi.seller_id
LEFT JOIN (
  SELECT order_id, AVG(review_score) AS review_score FROM order_reviews GROUP BY order_id
) rv ON rv.order_id = oi.order_id
WHERE o.order_purchase_timestamp IS NOT NULL
GROUP BY 1, 2, 3;

DROP TABLE IF EXISTS mv_payment_dist;
CREATE TABLE mv_payment_dist (
  `year_month` CHAR(7) NOT NULL,
  payment_type VARCHAR(48) NOT NULL,
  total_transactions INT NOT NULL,
  avg_installments DECIMAL(12, 4) NOT NULL,
  total_value DECIMAL(18,2) NOT NULL,
  PRIMARY KEY (`year_month`, payment_type),
  INDEX idx_pay_ym (`year_month`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO mv_payment_dist (
  `year_month`, payment_type, total_transactions, avg_installments, total_value
)
SELECT DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS `year_month`,
       pay.payment_type,
       COUNT(*) AS total_transactions,
       AVG(CAST(pay.payment_installments AS DECIMAL(14, 4))) AS avg_installments,
       SUM(pay.payment_value) AS total_value
FROM payments pay
JOIN orders o ON o.order_id = pay.order_id
WHERE o.order_purchase_timestamp IS NOT NULL
GROUP BY 1, 2;
