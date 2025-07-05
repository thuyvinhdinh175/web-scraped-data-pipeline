-- models/fact_price_history.sql
{{
  config(
    materialized = 'table',
    schema = 'gold',
    unique_key = ['product_id', 'scrape_date'],
    partition_by = {
      "field": "scrape_date",
      "data_type": "date",
      "granularity": "day"
    }
  )
}}

-- Create a historical price fact table to track price changes over time
WITH product_prices AS (
    SELECT
        product_id,
        name,
        brand,
        category,
        price,
        DATE(scrape_timestamp) AS scrape_date
    FROM {{ source('silver', 'products') }}
),

-- Get price from previous day for each product to calculate changes
previous_prices AS (
    SELECT
        product_id,
        scrape_date,
        price,
        LAG(price) OVER (
            PARTITION BY product_id, category
            ORDER BY scrape_date
        ) AS previous_price,
        LAG(scrape_date) OVER (
            PARTITION BY product_id, category
            ORDER BY scrape_date
        ) AS previous_date
    FROM product_prices
),

-- Calculate moving averages and other price metrics
price_metrics AS (
    SELECT
        p.product_id,
        p.name AS product_name,
        p.brand,
        p.category,
        p.price AS current_price,
        p.scrape_date,
        prev.previous_price,
        prev.previous_date,
        CASE
            WHEN prev.previous_price IS NULL THEN 0
            ELSE (p.price - prev.previous_price) / prev.previous_price
        END AS price_change_pct,
        AVG(p.price) OVER (
            PARTITION BY p.product_id, p.category
            ORDER BY p.scrape_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS price_7day_avg,
        AVG(p.price) OVER (
            PARTITION BY p.product_id, p.category
            ORDER BY p.scrape_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS price_30day_avg,
        MIN(p.price) OVER (
            PARTITION BY p.product_id, p.category
            ORDER BY p.scrape_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS price_30day_min,
        MAX(p.price) OVER (
            PARTITION BY p.product_id, p.category
            ORDER BY p.scrape_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS price_30day_max
    FROM product_prices p
    LEFT JOIN previous_prices prev
        ON p.product_id = prev.product_id
        AND p.scrape_date = prev.scrape_date
)

SELECT
    product_id,
    product_name,
    brand,
    category,
    current_price,
    previous_price,
    price_change_pct,
    price_7day_avg,
    price_30day_avg,
    price_30day_min,
    price_30day_max,
    -- Price trend indicators
    CASE
        WHEN price_change_pct > 0.05 THEN 'Rising'
        WHEN price_change_pct < -0.05 THEN 'Falling'
        ELSE 'Stable'
    END AS price_trend,
    -- Is current price below/above average
    CASE
        WHEN current_price < price_30day_avg * 0.95 THEN 'Good Deal'
        WHEN current_price > price_30day_avg * 1.05 THEN 'Premium Pricing'
        ELSE 'Normal Pricing'
    END AS price_status,
    -- Is price at or near 30-day min/max
    CASE
        WHEN current_price <= price_30day_min * 1.01 THEN true
        ELSE false
    END AS is_at_30day_low,
    CASE
        WHEN current_price >= price_30day_max * 0.99 THEN true
        ELSE false
    END AS is_at_30day_high,
    scrape_date
FROM price_metrics
