CREATE TABLE users (
    user_id INTEGER PRIMARY KEY CHECK (user_id > 0),
    balance_cents INTEGER NOT NULL DEFAULT 0 CHECK (balance_cents >= 0)
);
