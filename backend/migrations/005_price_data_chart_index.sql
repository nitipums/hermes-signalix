-- Chart API index: match the case-insensitive ORD chart query.
CREATE INDEX IF NOT EXISTS price_data_th_ord_upper_symbol_date_idx
ON price_data (market, instrument_type, upper(symbol), date DESC);
