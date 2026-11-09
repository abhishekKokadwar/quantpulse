-- Financial Non-Negativity Contract:
-- Executed prices, trade quantities, and notional USD amounts must strictly be positive.
-- Returns any corrupt or inverted records.

SELECT
    trade_id,
    symbol,
    timestamp,
    price,
    quantity,
    notional_usd
FROM {{ ref('silver_trades_clean') }}
WHERE price <= 0.0
   OR quantity <= 0.0
   OR notional_usd <= 0.0
