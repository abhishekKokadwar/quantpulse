{{ config(materialized='table') }}

WITH raw AS (
    SELECT * FROM {{ ref('bronze_raw_trades') }}
),

deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, timestamp, trade_id
            ORDER BY timestamp ASC
        ) AS dedup_rank
    FROM raw
),

cleaned AS (
    SELECT
        d.trade_id,
        d.symbol,
        d.exchange,
        d.asset_class,
        d.timestamp,
        d.price,
        d.quantity,
        d.side AS raw_side,
        d.is_buyer_maker,
        d.liquidation,
        ROUND(d.price * d.quantity, 2) AS notional_usd,
        d.bid_1,
        d.ask_1,
        d.spread,
        d.mid_price,
        d.micro_price,
        d.order_flow_imbalance,
        -- Lee-Ready Trade Aggressor Classification Algorithm
        CASE
            WHEN d.price > d.mid_price THEN 'BUY'
            WHEN d.price < d.mid_price THEN 'SELL'
            WHEN d.is_buyer_maker THEN 'SELL'
            WHEN NOT d.is_buyer_maker THEN 'BUY'
            ELSE COALESCE(d.side, 'BUY')
        END AS aggressor_side,
        -- Spread in basis points
        CASE
            WHEN d.mid_price > 0 THEN ROUND(10000.0 * (d.ask_1 - d.bid_1) / d.mid_price, 4)
            ELSE 0.0
        END AS spread_bps,
        -- Non-crossing arbitrage validity flag
        CASE
            WHEN d.ask_1 > d.bid_1 THEN TRUE
            ELSE FALSE
        END AS is_valid_quote_spread,
        COALESCE(i.base_currency, SPLIT_PART(d.symbol, '/', 1)) AS base_currency,
        COALESCE(i.quote_currency, 'USD') AS quote_currency,
        COALESCE(i.tick_size, 0.01) AS tick_size,
        COALESCE(i.lot_size, 1.0) AS lot_size,
        d._ingested_at,
        d._source_file
    FROM deduped d
    LEFT JOIN {{ ref('stg_instruments') }} i ON d.symbol = i.symbol
    WHERE d.dedup_rank = 1
      AND d.price > 0
      AND d.quantity > 0
      AND d.timestamp IS NOT NULL
)

SELECT * FROM cleaned
