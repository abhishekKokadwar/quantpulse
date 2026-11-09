{{ config(materialized='view') }}

SELECT
    trade_id::BIGINT AS trade_id,
    symbol::VARCHAR AS symbol,
    exchange::VARCHAR AS exchange,
    asset_class::VARCHAR AS asset_class,
    timestamp::TIMESTAMPTZ AS timestamp,
    price::DOUBLE AS price,
    quantity::DOUBLE AS quantity,
    side::VARCHAR AS side,
    is_buyer_maker::BOOLEAN AS is_buyer_maker,
    COALESCE(liquidation, false)::BOOLEAN AS liquidation,
    notional_usd::DOUBLE AS notional_usd,
    bid_1::DOUBLE AS bid_1,
    ask_1::DOUBLE AS ask_1,
    spread::DOUBLE AS spread,
    mid_price::DOUBLE AS mid_price,
    micro_price::DOUBLE AS micro_price,
    order_flow_imbalance::DOUBLE AS order_flow_imbalance,
    symbol_clean::VARCHAR AS symbol_clean,
    current_timestamp AS _ingested_at,
    filename::VARCHAR AS _source_file,
    row_number() OVER () AS _file_row_number
FROM read_parquet('{{ var("raw_trades_glob") }}', filename=true, hive_partitioning=1, union_by_name=true)
