CREATE TABLE bank_accounts (
    user_id INTEGER PRIMARY KEY
        REFERENCES users(user_id) ON DELETE CASCADE,
    balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
    level INTEGER NOT NULL DEFAULT 1 CHECK (level >= 1)
);
