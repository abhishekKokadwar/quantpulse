{{ config(materialized='table') }}

WITH trades AS (
    SELECT * FROM {{ ref('silver_trades_clean') }}
),

aggregated AS (
    SELECT
        time_bucket(INTERVAL '1 MINUTE', timestamp) AS bar_time,
        symbol,
        asset_class,
        arg_min(price, timestamp) AS open_price,
        MAX(price) AS high_price,
        MIN(price) AS low_price,
        arg_max(price, timestamp) AS close_price,
        ROUND(SUM(quantity), 6) AS volume,
        COUNT(*) AS trade_count,
        ROUND(SUM(price * quantity) / NULLIF(SUM(quantity), 0), 6) AS vwap,
        ROUND(SUM(notional_usd), 2) AS notional_usd,
        ROUND(SUM(CASE WHEN aggressor_side = 'BUY' THEN quantity ELSE 0 END), 6) AS buy_volume,
        ROUND(SUM(CASE WHEN aggressor_side = 'SELL' THEN quantity ELSE 0 END), 6) AS sell_volume,
        ROUND(SUM(CASE WHEN aggressor_side = 'BUY' THEN quantity ELSE -quantity END), 6) AS cvd,
        ROUND(AVG(spread_bps), 4) AS avg_spread_bps,
        ROUND(AVG(order_flow_imbalance), 4) AS avg_ofi
    FROM trades
    GROUP BY 1, 2, 3
)

SELECT
    symbol || '_' || strftime(bar_time, '%Y%m%d%H%M%S') AS bar_id,
    bar_time,
    symbol,
    asset_class,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    trade_count,
    COALESCE(vwap, close_price) AS vwap,
    notional_usd,
    buy_volume,
    sell_volume,
    cvd,
    avg_spread_bps,
    avg_ofi
FROM aggregated
ORDER BY bar_time ASC, symbol ASC
