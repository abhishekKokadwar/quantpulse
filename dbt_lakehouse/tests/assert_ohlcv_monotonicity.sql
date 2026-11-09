-- Monotonicity Contract:
-- High price must be >= both Open and Close price, and
-- Low price must be <= both Open and Close price for every OHLCV bar.
-- Returns any bar violating mathematical candle envelope monotonicity.

SELECT
    bar_id,
    symbol,
    bar_time,
    open_price,
    high_price,
    low_price,
    close_price
FROM {{ ref('silver_ohlcv_1m') }}
WHERE high_price < open_price
   OR high_price < close_price
   OR low_price > open_price
   OR low_price > close_price
