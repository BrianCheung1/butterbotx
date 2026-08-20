CREATE TABLE mining_profiles (
    user_id INTEGER PRIMARY KEY
        REFERENCES users(user_id) ON DELETE CASCADE,
    xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
    total_actions INTEGER NOT NULL DEFAULT 0 CHECK (total_actions >= 0),
    total_earned INTEGER NOT NULL DEFAULT 0 CHECK (total_earned >= 0),
    next_mine_at TEXT NOT NULL
);
