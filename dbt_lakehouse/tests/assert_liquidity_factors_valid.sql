-- Institutional Liquidity Sanity Contract:
-- Kyle's Lambda and Amihud Illiquidity ratios must be non-negative.
-- Returns any invalid inverted records.

SELECT
    liquidity_id,
    symbol,
    trade_date,
    kyle_lambda,
    amihud_illiquidity
FROM {{ ref('fct_daily_market_liquidity') }}
WHERE kyle_lambda < 0.0
   OR amihud_illiquidity < 0.0
