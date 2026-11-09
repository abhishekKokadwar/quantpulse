-- Arbitrage Boundary Condition:
-- Quotes must never be crossed (Ask price must be strictly greater than Bid price).
-- Returns any records that violate the non-crossing boundary condition.

SELECT
    trade_id,
    symbol,
    timestamp,
    bid_1,
    ask_1,
    spread
FROM {{ ref('silver_trades_clean') }}
WHERE ask_1 <= bid_1
