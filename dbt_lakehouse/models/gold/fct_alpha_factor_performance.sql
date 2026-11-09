{{ config(materialized='table') }}

WITH bars AS (
    SELECT
        bar_time,
        symbol,
        asset_class,
        close_price,
        cvd,
        avg_ofi
    FROM {{ ref('silver_ohlcv_1m') }}
),

returns_lagged AS (
    SELECT
        bar_time,
        symbol,
        asset_class,
        close_price,
        cvd,
        avg_ofi,
        LAG(close_price) OVER (PARTITION BY symbol ORDER BY bar_time ASC) AS prev_close
    FROM bars
),

bar_returns AS (
    SELECT
        bar_time,
        symbol,
        asset_class,
        close_price,
        COALESCE((close_price - prev_close) / NULLIF(prev_close, 0), 0.0) AS asset_return,
        -- Institutional Order Flow Momentum Alpha Signal
        CASE
            WHEN avg_ofi > 0.05 OR cvd > 0 THEN 1.0
            WHEN avg_ofi < -0.05 OR cvd < 0 THEN -1.0
            ELSE 0.0
        END AS alpha_signal,
        COALESCE(
            (CASE
                WHEN avg_ofi > 0.05 OR cvd > 0 THEN 1.0
                WHEN avg_ofi < -0.05 OR cvd < 0 THEN -1.0
                ELSE 0.0
            END) * ((close_price - prev_close) / NULLIF(prev_close, 0)),
            0.0
        ) AS strategy_return
    FROM returns_lagged
),

cum_returns AS (
    SELECT
        bar_time,
        symbol,
        asset_class,
        strategy_return,
        SUM(strategy_return) OVER (PARTITION BY symbol ORDER BY bar_time ASC) AS cum_return
    FROM bar_returns
),

peak_tracking AS (
    SELECT
        *,
        MAX(cum_return) OVER (PARTITION BY symbol ORDER BY bar_time ASC) AS peak_cum_return
    FROM cum_returns
),

drawdowns AS (
    SELECT
        *,
        (peak_cum_return - cum_return) AS drawdown
    FROM peak_tracking
),

performance_metrics AS (
    SELECT
        symbol,
        asset_class,
        COUNT(*) AS observation_bars,
        ROUND(SUM(strategy_return), 6) AS cumulative_strategy_return,
        ROUND(AVG(strategy_return), 6) AS mean_bar_return,
        ROUND(COALESCE(STDDEV(strategy_return), 0.0001), 6) AS vol_bar_return,
        ROUND(AVG(strategy_return) * 252 * 390, 4) AS annualized_return,
        ROUND(COALESCE(STDDEV(strategy_return), 0.0001) * SQRT(252.0 * 390.0), 4) AS annualized_volatility,
        ROUND(
            (AVG(strategy_return) * SQRT(252.0 * 390.0)) /
            NULLIF(COALESCE(STDDEV(strategy_return), 0.0001) * SQRT(252.0 * 390.0), 0),
            4
        ) AS sharpe_ratio,
        ROUND(
            (AVG(strategy_return) * SQRT(252.0 * 390.0)) /
            NULLIF(SQRT(AVG(CASE WHEN strategy_return < 0 THEN strategy_return * strategy_return ELSE 0.00000001 END)) * SQRT(252.0 * 390.0), 0),
            4
        ) AS sortino_ratio,
        ROUND(MAX(drawdown), 6) AS max_drawdown,
        ROUND(
            (AVG(strategy_return) * 252.0 * 390.0) /
            NULLIF(MAX(drawdown), 0),
            4
        ) AS calmar_ratio,
        ROUND(100.0 * COUNT(CASE WHEN strategy_return > 0 THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS win_rate_pct
    FROM drawdowns
    GROUP BY 1, 2
)

SELECT
    symbol || '_alpha_perf' AS performance_id,
    symbol,
    asset_class,
    observation_bars,
    cumulative_strategy_return,
    mean_bar_return,
    vol_bar_return,
    annualized_return,
    annualized_volatility,
    COALESCE(sharpe_ratio, 0.0) AS sharpe_ratio,
    COALESCE(sortino_ratio, 0.0) AS sortino_ratio,
    COALESCE(max_drawdown, 0.0) AS max_drawdown,
    COALESCE(calmar_ratio, 0.0) AS calmar_ratio,
    win_rate_pct,
    current_timestamp AS evaluated_at
FROM performance_metrics
ORDER BY sharpe_ratio DESC
