-- 性能对比实验示例（任选一组与报告截图对应）
-- 说明：请将「毫秒/秒级」耗时与 Rows examined 截取到报告中。

USE olist_agentic_bi;

-- 例 1：2017 年各月 GMV 趋势 ----------------------------------------------

-- [快] 读取预聚合表
SELECT `year_month`,
       SUM(total_gmv) AS gmv_by_month
FROM mv_monthly_sales
WHERE `year_month` LIKE '2017-%'
GROUP BY `year_month`
ORDER BY `year_month`;


-- [慢] 原始多表聚合（等价业务口径示意）
SELECT DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS ym,
       SUM(oi.price + oi.freight_value) AS gmv_live
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_purchase_timestamp >= '2017-01-01'
  AND o.order_purchase_timestamp <  '2018-01-01'
GROUP BY ym
ORDER BY ym;


-- 例 2：2017-Q4 支付方式占比 ------------------------------------------------

-- [快]
SELECT payment_type,
       SUM(total_transactions) AS tx_cnt
FROM mv_payment_dist
WHERE `year_month` BETWEEN '2017-10' AND '2017-12'
GROUP BY payment_type
ORDER BY tx_cnt DESC;


-- [慢]
SELECT pay.payment_type,
       COUNT(*) AS tx_cnt
FROM payments pay
JOIN orders o ON o.order_id = pay.order_id
WHERE o.order_purchase_timestamp >= '2017-10-01'
  AND o.order_purchase_timestamp <  '2018-01-01'
GROUP BY pay.payment_type
ORDER BY tx_cnt DESC;
