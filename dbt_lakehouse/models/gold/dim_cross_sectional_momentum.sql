{{ config(materialized='table') }}

WITH bars AS (
    SELECT * FROM {{ ref('silver_ohlcv_1m') }}
),

symbol_summary AS (
    SELECT
        symbol,
        asset_class,
        arg_min(open_price, bar_time) AS initial_price,
        arg_max(close_price, bar_time) AS latest_price,
        MAX(high_price) AS max_price,
        MIN(low_price) AS min_price,
        SUM(volume) AS total_volume,
        SUM(trade_count) AS total_trades,
        ROUND(SUM(vwap * volume) / NULLIF(SUM(volume), 0), 6) AS universe_vwap,
        ROUND(
            (arg_max(close_price, bar_time) - arg_min(open_price, bar_time)) /
            NULLIF(arg_min(open_price, bar_time), 0),
            6
        ) AS momentum_return,
        ROUND(
            100.0 * (arg_max(close_price, bar_time) - arg_min(open_price, bar_time)) /
            NULLIF(arg_min(open_price, bar_time), 0),
            4
        ) AS momentum_return_pct
    FROM bars
    GROUP BY 1, 2
),

ranked AS (
    SELECT
        symbol || '_momentum' AS momentum_id,
        symbol,
        asset_class,
        initial_price,
        latest_price,
        max_price,
        min_price,
        ROUND(total_volume, 4) AS total_volume,
        total_trades,
        universe_vwap,
        momentum_return,
        momentum_return_pct,
        DENSE_RANK() OVER (
            PARTITION BY asset_class
            ORDER BY momentum_return DESC
        ) AS class_rank,
        COUNT(*) OVER (
            PARTITION BY asset_class
        ) AS class_asset_count,
        DENSE_RANK() OVER (
            ORDER BY momentum_return DESC
        ) AS global_rank,
        ROUND(
            PERCENT_RANK() OVER (
                ORDER BY momentum_return ASC
            ),
            4
        ) AS momentum_percentile,
        CASE
            WHEN PERCENT_RANK() OVER (ORDER BY momentum_return ASC) >= 0.80 THEN 'LONG_TOP_QUINTILE'
            WHEN PERCENT_RANK() OVER (ORDER BY momentum_return ASC) <= 0.20 THEN 'SHORT_BOTTOM_QUINTILE'
            ELSE 'NEUTRAL'
        END AS factor_signal
    FROM symbol_summary
)

SELECT
    momentum_id,
    symbol,
    asset_class,
    initial_price,
    latest_price,
    max_price,
    min_price,
    total_volume,
    total_trades,
    universe_vwap,
    momentum_return,
    momentum_return_pct,
    class_rank,
    class_asset_count,
    global_rank,
    momentum_percentile,
    factor_signal,
    current_timestamp AS ranked_at
FROM ranked
ORDER BY global_rank ASC
