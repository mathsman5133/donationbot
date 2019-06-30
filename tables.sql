CREATE TABLE players (
    id serial PRIMARY KEY,

    player_tag TEXT UNIQUE,
    donations INTEGER,
    received INTEGER,
    user_id BIGINT,
    clan_tag TEXT,
    last_updated TIMESTAMP
    );

CREATE TABLE clans (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    clan_tag TEXT,
    clan_name TEXT
    );

CREATE TABLE guilds (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    log_channel_id BIGINT,
    log_toggle BOOLEAN,
    updates_channel_id BIGINT,
    updates_message_id BIGINT,
    updates_toggle BOOLEAN,
    updates_ign BOOLEAN,
    updates_don BOOLEAN,
    updates_rec BOOLEAN,
    updates_tag BOOLEAN,
    updates_claimed_by BOOLEAN
    );

CREATE TABLE messages (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    message_id BIGINT

    );

CREATE TABLE commands (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    channel_id BIGINT,
    author_id BIGINT,
    used TIMESTAMP,
    prefix TEXT,
    command TEXT,
    failed BOOLEAN
);