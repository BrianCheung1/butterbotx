CREATE TABLE daily_claims (
    user_id INTEGER PRIMARY KEY
        REFERENCES users(user_id) ON DELETE CASCADE,
    streak INTEGER NOT NULL CHECK (streak >= 0),
    last_claim_date TEXT NOT NULL CHECK (
        length(last_claim_date) = 10
        AND last_claim_date GLOB
            '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
    )
);
