CREATE SCHEMA IF NOT EXISTS vm_projection;

CREATE TABLE IF NOT EXISTS vm_projection.cursors (
    cluster_id TEXT PRIMARY KEY,
    event_seq BIGINT NOT NULL DEFAULT 0 CHECK (event_seq >= 0),
    market_seq BIGINT NOT NULL DEFAULT 0 CHECK (market_seq >= 0),
    events_stored BIGINT NOT NULL DEFAULT 0 CHECK (events_stored >= 0),
    trades_stored BIGINT NOT NULL DEFAULT 0 CHECK (trades_stored >= 0),
    batches_committed BIGINT NOT NULL DEFAULT 0 CHECK (batches_committed >= 0),
    source_last_event_seq BIGINT NOT NULL DEFAULT 0 CHECK (source_last_event_seq >= event_seq),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS vm_projection.events (
    cluster_id TEXT NOT NULL REFERENCES vm_projection.cursors(cluster_id),
    event_seq BIGINT NOT NULL CHECK (event_seq > 0),
    market_seq BIGINT NOT NULL CHECK (market_seq >= 0),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    stored_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (cluster_id, event_seq)
);

CREATE UNIQUE INDEX IF NOT EXISTS events_public_sequence
    ON vm_projection.events(cluster_id, market_seq) WHERE market_seq > 0;

CREATE OR REPLACE VIEW vm_projection.public_market_events WITH (security_barrier = true) AS
    SELECT cluster_id, market_seq,
           jsonb_build_object(
               'marketSeq', market_seq,
               'type', event_type,
               'side', payload -> 'side',
               'priceTicks', payload -> 'priceTicks',
               'quantityLots', payload -> 'quantityLots'
           ) AS payload
    FROM vm_projection.events
    WHERE market_seq > 0
      AND event_type IN ('ORDER_ACCEPTED', 'TRADE', 'ORDER_CANCELLED', 'ORDER_EXPIRED');

REVOKE ALL ON vm_projection.events, vm_projection.cursors FROM PUBLIC;
REVOKE ALL ON vm_projection.public_market_events FROM PUBLIC;
