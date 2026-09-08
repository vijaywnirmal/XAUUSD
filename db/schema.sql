-- XAUUSD Postgres schema: bars (OHLC) + full tick archive.
-- Tick tables are RANGE-partitioned by year (2009-2027) for load/query manageability.
-- Indexes are created separately (see migrate.py) AFTER bulk load for speed.

CREATE TABLE IF NOT EXISTS bars_1min (
    ts             TIMESTAMPTZ NOT NULL,
    open           DOUBLE PRECISION,
    high           DOUBLE PRECISION,
    low            DOUBLE PRECISION,
    close          DOUBLE PRECISION,
    bid_close      DOUBLE PRECISION,
    ask_close      DOUBLE PRECISION,
    tick_count     INTEGER,
    spread_mean    DOUBLE PRECISION,
    spread_median  DOUBLE PRECISION,
    volume_sum     DOUBLE PRECISION,
    source         SMALLINT
);

CREATE TABLE IF NOT EXISTS bars_5min (LIKE bars_1min INCLUDING ALL);
CREATE TABLE IF NOT EXISTS bars_15min (LIKE bars_1min INCLUDING ALL);

-- Tick archive, partitioned by year. One table per side (bid/ask), matching
-- the existing canonical/{bid,ask}/ parquet layout.
CREATE TABLE IF NOT EXISTS ticks_bid (
    time_msc  BIGINT,
    time      TIMESTAMPTZ NOT NULL,
    price     DOUBLE PRECISION,
    volume    DOUBLE PRECISION,
    flags     INTEGER,
    source    SMALLINT
) PARTITION BY RANGE (time);

CREATE TABLE IF NOT EXISTS ticks_ask (LIKE ticks_bid) PARTITION BY RANGE (time);

-- Yearly partitions 2009-2027 for both sides (covers the 2009-01 -> 2026-09 archive
-- plus one year of headroom).
DO $$
DECLARE
    yr INT;
BEGIN
    FOR yr IN 2009..2027 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS ticks_bid_%s PARTITION OF ticks_bid FOR VALUES FROM (%L) TO (%L)',
            yr, format('%s-01-01', yr), format('%s-01-01', yr + 1)
        );
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS ticks_ask_%s PARTITION OF ticks_ask FOR VALUES FROM (%L) TO (%L)',
            yr, format('%s-01-01', yr), format('%s-01-01', yr + 1)
        );
    END LOOP;
END $$;
