import os
from dotenv import load_dotenv
load_dotenv()

POSTGRESQL_URL = os.getenv("POSTGRESQL_URL")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

BOT_PREFIX = ">"

GUILD_ID = 1242575090433130496

VALOR_RED1 = 0xB20101
VALOR_RED2 = 0x8B0201
VALOR_RED3 = 0x150201
VALOR_YELLOW = 0xFFD700

DATABASE_TABLES = {
    "bot_settings": {
        "guild_id": "BIGINT NOT NULL PRIMARY KEY",
        "mm_buttons_channel": "BIGINT",
        "mm_queue_channel": "BIGINT",
        "mm_queue_message": "BIGINT",
        "mm_queue_periods": "TEXT",
        "mm_log_channel": "BIGINT",
        "staff_channel": "BIGINT",
        "log_channel": "BIGINT"
    },
    "mm_bot_queue_users": {
        "user_id": "BIGINT NOT NULL",
        "queue_channel": "BIGINT NOT NULL",
        "queue_expiry": "INTEGER",
        "PRIMARY KEY": "(user_id, queue_channel)"
    },
    "mm_bot_users": {
        "id": "SERIAL PRIMARY KEY",
        "guild_id": "BIGINT NOT NULL",
        "user_id": "BIGINT NOT NULL",
        "display_name": "VARCHAR(32)",
        "mmr": "INTEGER NOT NULL DEFAULT 800000",
        "games": "INTEGER DEFAULT 0",
        "wins": "INTEGER DEFAULT 0",
        "loss": "INTEGER DEFAULT 0",
        "team_a": "INTEGER DEFAULT 0",
        "joined_timestamp": "TIMESTAMP WITH TIME ZONE DEFAULT now()",
        "UNIQUE": "(guild_id, user_id)"
    },
    "mm_bot_matches": {
        "id": "SERIAL PRIMARY KEY",
        "match_thread": "BIGINT",
        "a_thread": "BIGINT",
        "b_thread": "BIGINT",
        "a_vc": "BIGINT",
        "b_vc": "BIGINT",
        "map": "VARCHAR(32) NOT NULL",
        "a_bans": "VARCHAR(32)[]",
        "b_bans": "VARCHAR(32)[]",
        "a_score": "SMALLINT",
        "b_score": "SMALLINT",
        "start_timestamp": "INTEGER NOT NULL"
    },
    "mm_bot_match_users": {
        "user_id": "BIGINT NOT NULL",
        "match_id": "BIGINT NOT NULL",
        "team": "VARCHAR(1) NOT NULL",
        "PRIMARY KEY": "(user_id, match_id)",
        "FOREIGN KEY (user_id)": "REFERENCES mm_bot_users(user_id)",
        "FOREIGN KEY (match_id)": "REFERENCES mm_bot_matches(id)"
    },
    "mm_bot_match_history": {
        "id": "SERIAL PRIMARY KEY",
        "a_team": "BIGINT[]",
        "b_team": "BIGINT[]",
        "map": "VARCHAR(32) NOT NULL",
        "a_bans": "VARCHAR(32)[]",
        "b_bans": "VARCHAR(32)[]",
        "a_score": "SMALLINT NOT NULL",
        "b_score": "SMALLINT NOT NULL",
        "start_timestamp": "INTEGER NOT NULL",
        "end_timestamp": "INTEGER NOT NULL"
    },
    "mm_bot_mmr_history": {
        "id": "SERIAL PRIMARY KEY",
        "guild_id": "BIGINT NOT NULL",
        "user_id": "BIGINT NOT NULL",
        "mmr": "INTEGER NOT NULL",
        "mmr_delta": "INTEGER NOT NULL",
        "timestamp": "TIMESTAMP WITH TIMEZONE DEFAULT now()",
        "FOREIGN KEY (user_id)": "REFERENCES mm_bot_users(user_id)"
    }
}