{{ config(materialized='view') }}

SELECT
    symbol,
    asset_class,
    base_currency,
    quote_currency,
    CAST(ref_price AS DOUBLE) AS ref_price,
    CAST(tick_size AS DOUBLE) AS tick_size,
    CAST(lot_size AS DOUBLE) AS lot_size,
    CAST(annual_vol AS DOUBLE) AS annual_vol,
    exchange_primary
FROM {{ ref('seed_instruments') }}
