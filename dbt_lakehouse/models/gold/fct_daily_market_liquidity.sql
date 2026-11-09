{{ config(materialized='table') }}

WITH bars AS (
    SELECT * FROM {{ ref('silver_ohlcv_1m') }}
),

daily_agg AS (
    SELECT
        date_trunc('day', bar_time) AS trade_date,
        symbol,
        asset_class,
        arg_min(open_price, bar_time) AS day_open,
        MAX(high_price) AS day_high,
        MIN(low_price) AS day_low,
        arg_max(close_price, bar_time) AS day_close,
        ROUND(SUM(volume), 6) AS total_volume,
        SUM(trade_count) AS total_trades,
        ROUND(SUM(notional_usd), 2) AS total_notional_usd,
        ROUND(SUM(vwap * volume) / NULLIF(SUM(volume), 0), 6) AS day_vwap,
        ROUND(AVG(avg_spread_bps), 4) AS avg_spread_bps,
        ROUND(SUM(cvd), 6) AS net_cvd
    FROM bars
    GROUP BY 1, 2, 3
),

metrics AS (
    SELECT
        symbol || '_' || strftime(trade_date, '%Y%m%d') AS liquidity_id,
        trade_date,
        symbol,
        asset_class,
        day_open,
        day_high,
        day_low,
        day_close,
        total_volume,
        total_trades,
        total_notional_usd,
        COALESCE(day_vwap, day_close) AS day_vwap,
        avg_spread_bps,
        net_cvd,
        ROUND(ABS(day_close - day_open), 6) AS abs_price_change,
        ROUND(100.0 * (day_close - day_open) / NULLIF(day_open, 0), 4) AS return_pct,
        -- Kyle's Lambda: Price impact coefficient per unit volume
        ROUND(ABS(day_close - day_open) / NULLIF(total_volume, 0), 8) AS kyle_lambda,
        -- Amihud Illiquidity Ratio (scaled by 10^6)
        ROUND(1000000.0 * (ABS(day_close - day_open) / NULLIF(day_open, 0)) / NULLIF(total_notional_usd, 0), 8) AS amihud_illiquidity
    FROM daily_agg
)

SELECT * FROM metrics
ORDER BY trade_date ASC, symbol ASC
