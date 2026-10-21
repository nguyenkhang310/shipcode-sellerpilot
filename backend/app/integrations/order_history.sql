-- One journal for SQLite writers: seller web, app, payments and simulator.
-- Triggers participate in the caller's transaction; rollback removes events.
CREATE TABLE IF NOT EXISTS sellerpilot_order_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,
    shop_slug TEXT NOT NULL,
    order_id INTEGER NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    changed_fields TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sellerpilot_order_event_shop_order
    ON sellerpilot_order_event(shop_slug, order_id, id);
CREATE TABLE IF NOT EXISTS sellerpilot_order_shipping (
    shop_slug TEXT NOT NULL, order_id INTEGER NOT NULL, carrier TEXT NOT NULL,
    tracking_number TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(shop_slug, order_id)
);
CREATE TABLE IF NOT EXISTS sellerpilot_order_receipt (
    operation_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL,
    shop_slug TEXT NOT NULL, order_id INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS sellerpilot_order_history_cleanup
AFTER DELETE ON "order"
BEGIN
    DELETE FROM sellerpilot_order_event WHERE order_id = OLD.id;
    DELETE FROM sellerpilot_order_shipping WHERE order_id = OLD.id;
    DELETE FROM sellerpilot_order_receipt WHERE order_id = OLD.id;
END;
CREATE TRIGGER IF NOT EXISTS sellerpilot_order_status_history
AFTER UPDATE OF status ON "order"
WHEN OLD.status IS NOT NEW.status
BEGIN
    INSERT INTO sellerpilot_order_event
        (operation_id, shop_slug, order_id, from_status, to_status, changed_fields, created_at)
    VALUES ('status:' || lower(hex(randomblob(16))),
        COALESCE((SELECT slug FROM shop WHERE id = NEW.shop_id), 'local'),
        NEW.id, COALESCE(OLD.status, ''), COALESCE(NEW.status, ''), '["status"]',
        strftime('%Y-%m-%dT%H:%M:%f', 'now'));
END;
-- An imported/generated order may already be delivered. Record its initial
-- state, without inventing confirmation/shipping/delivery timestamps.
CREATE TRIGGER IF NOT EXISTS sellerpilot_order_initial_history
AFTER INSERT ON "order"
WHEN NEW.status IS NOT 'pending'
BEGIN
    INSERT INTO sellerpilot_order_event
        (operation_id, shop_slug, order_id, from_status, to_status, changed_fields, created_at)
    VALUES ('initial:' || lower(hex(randomblob(16))),
        COALESCE((SELECT slug FROM shop WHERE id = NEW.shop_id), 'local'),
        NEW.id, COALESCE(NEW.status, ''), COALESCE(NEW.status, ''), '["status"]',
        strftime('%Y-%m-%dT%H:%M:%f', 'now'));
END;
