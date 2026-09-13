-- Reference DDL; indexes are applied automatically by app/db/migrator.py on startup.
CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_session_status ON orders(customer_session_id, status, id);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status_end ON boardroom_bookings(status, expected_end_at);
CREATE INDEX IF NOT EXISTS idx_receivables_paid_paid_at ON receivables(paid, paid_at);
